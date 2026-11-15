"""Recognize local bonus videos and associate them using folder context.

Folder conventions are documented by:
https://support.plex.tv/articles/local-files-for-trailers-and-extras/
https://support.plex.tv/articles/local-files-for-tv-show-trailers-and-extras/
https://jellyfin.org/docs/general/server/media/movies/
https://www.emby.media/support/articles/Movie-Naming.html
"""
import os
import re
from pathlib import Path

EXTRA_FOLDERS = {
    'behindthescenes': 'Behind The Scenes', 'makingof': 'Behind The Scenes',
    'deletedscenes': 'Deleted Scenes', 'deleted': 'Deleted Scenes',
    'interviews': 'Interviews', 'interview': 'Interviews',
    'featurettes': 'Featurettes', 'featurette': 'Featurettes',
    'trailers': 'Trailers', 'trailer': 'Trailers',
    'scenes': 'Scenes', 'scene': 'Scenes', 'shorts': 'Shorts', 'short': 'Shorts',
    'extras': 'Other', 'extra': 'Other', 'other': 'Other', 'bonus': 'Other',
    'bonusfeatures': 'Other', 'bonusdisc': 'Other', 'specialfeatures': 'Other',
    'specialeditionbonuses': 'Other', 'bonusmaterial': 'Other',
    'specials': 'Other',
    'bloopers': 'Other', 'gagreel': 'Other',
}
EXTRA_TYPES = ['Behind The Scenes', 'Deleted Scenes', 'Featurettes', 'Interviews',
               'Scenes', 'Shorts', 'Trailers', 'Other']
SUFFIX = re.compile(r'(?i)-(?P<kind>behindthescenes|deleted|featurette|interview|scene|short|trailer|other)\d*$')


def folder_key(name):
    return re.sub(r'[^a-z0-9]', '', name.casefold())


def context(path, root):
    """Only explicit extras folders or suffixes classify a file as a bonus."""
    path, root = Path(path), Path(root)
    parts = path.relative_to(root).parts[:-1]
    for index, part in enumerate(parts):
        key = folder_key(part)
        category = EXTRA_FOLDERS.get(key)
        if re.fullmatch(r'bonus(?:disc|features)?[0-9]+',key):
            category = 'Other'
        if category:
            folder = root.joinpath(*parts[:index])
            nested_type = next((EXTRA_FOLDERS[folder_key(p)] for p in parts[index + 1:]
                                if folder_key(p) in EXTRA_FOLDERS), category)
            return folder, nested_type
    suffix = SUFFIX.search(path.stem)
    if suffix:
        return path.parent, EXTRA_FOLDERS[suffix['kind'].casefold()]
    return None


def inventory(root, excluded, video, is_link, parse):
    root = Path(root).resolve()
    media, extras = [], []
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d.casefold() != '.sortrr-trash'
                         and not is_link(Path(folder) / d)
                         and not any((Path(folder) / d).resolve().is_relative_to(p) for p in excluded))
        for name in sorted(names):
            path = Path(folder) / name
            if path.suffix.lower() not in video or is_link(path):
                continue
            try:
                item = parse(path)
                location = context(path, root)
                if item.season == 0 and any(folder_key(part) == 'specials' for part in path.relative_to(root).parts[:-1]):
                    location = None
            except OSError:
                continue
            # Database-numbered specials retain their episode semantics outside extras folders.
            if location:
                container, category = location
                extras.append({'path': str(path), 'folder': str(container), 'category': category,
                               'signature': list(item.signature), 'owner': '', 'reason': ''})
            else:
                media.append(item)

    for extra in extras:
        folder = Path(extra['folder'])
        candidates = [m for m in media if m.source.parent == folder]
        # A show-level extras folder can sit beside multiple season directories.
        if not candidates and folder != root:
            candidates = [m for m in media if m.source.is_relative_to(folder)]
        suffix = SUFFIX.search(Path(extra['path']).stem)
        if suffix:
            prefix = Path(extra['path']).stem[:suffix.start()]
            exact = [m for m in candidates if m.source.stem.casefold() == prefix.casefold()]
            if exact:
                candidates = exact
        identities = {(m.kind, folder_key(m.query), m.year) for m in candidates}
        if len(candidates) == 1 or (candidates and len(identities) == 1 and candidates[0].kind == 'TV'):
            extra['owner'] = str(candidates[0].source)
            extra['reason'] = 'Associated from its source folder'
        else:
            extra['reason'] = 'Choose the related movie or show'
    attach(media, extras)
    return media, extras


def attach(media, extras):
    owners = {str(m.source): m for m in media}
    for item in media:
        item.extras = []
    for extra in extras:
        owner = owners.get(extra['owner'])
        if owner:
            owner.extras.append(extra)


def targets(media, target, options):
    target = Path(target)
    base = target.parent
    if media.kind == 'TV' and options.show_layout == 'season':
        base = base.parent
    pairs = []
    for extra in media.extras:
        category = extra['category']
        if category == 'Other':
            category = {'none': 'Featurettes', 'emby': 'extras'}.get(options.id_style, 'Other')
        container = base
        if (media.kind == 'TV' and options.show_layout == 'season'
                and re.fullmatch(r'(?i)season[ ._-]*[0-9]+', Path(extra['folder']).name)):
            container = target.parent
        pairs.append((Path(extra['path']), container / category / Path(extra['path']).name))
    return pairs


def needs_sort(media, target, options):
    return any(source.resolve() != dest.resolve() for source, dest in targets(media,target,options))
