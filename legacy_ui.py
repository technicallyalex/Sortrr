import json, os, queue, threading, webbrowser, tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from previews import PreviewManager, VideoPreview, HoverScrubber
from core import DATA, VIDEO, Catalog, History, DatabaseSetupRequired, identify_batch, parse, destination, organize, undo, Media, SortOptions, MOVIE_LAYOUTS, SHOW_LAYOUTS, VIEW_SORT_FIELDS, sorted_media_indices, LAYOUT_PRESETS, ID_STYLES, preset_name, plan_renames, plan_cleanup, cleanup_empty_folders, apply_cleanup, sort_and_finish, unresolved_media, resolve_manually, entry_info_text

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Sortrr - Your library, in order'); self.geometry('1120x760'); self.minsize(850,720)
        self.items=[]; self.catalog=Catalog(); self.events=queue.Queue(); self.busy=False; self.journal=None; self.database_needed=False; self.pending_file_dialog=None
        self.previews=PreviewManager(DATA/'previews',lambda callback:self.events.put(('callback',callback)))
        self.thumbnail_timer=None; self.thumbnail_pending=set(); self.thumbnail_keys={}; self.thumbnail_images={}
        self.bind('<Destroy>',lambda event:self.previews.close() if event.widget==self else None)
        tokenfile=DATA/'tmdb-token.txt'
        if tokenfile.exists(): os.environ['SORTRR_TMDB_TOKEN']=tokenfile.read_text(encoding='utf-8').strip()
        self.in_place=tk.BooleanVar(value=False)
        self.options=SortOptions(); self.view_timer=None
        self.auto_rename=tk.BooleanVar(value=True); self.auto_cleanup=tk.BooleanVar(value=False)
        self.filter_var=tk.StringVar(value='All media'); self.sort_var=tk.StringVar(value='Source name'); self.descending=tk.BooleanVar(value=False)
        self.source=tk.StringVar(); self.library=tk.StringVar(); self.status=tk.StringVar(value='Choose your media folder and a library destination to get started.')
        try:
            config=json.loads((DATA/'settings.json').read_text()); self.source.set(config['source']); self.library.set(config['library']); self.in_place.set(config.get('in_place',False))
            self.options=SortOptions(**config.get('sorting',{}))
            self.auto_rename.set(self.options.rename_files); self.auto_cleanup.set(bool(config.get('auto_cleanup',False)))
            if config.get('media_filter') in ('All media','Movies','TV shows'): self.filter_var.set(config['media_filter'])
            if config.get('sort_by') in VIEW_SORT_FIELDS: self.sort_var.set(config['sort_by'])
            self.descending.set(bool(config.get('descending',False)))
        except (OSError,ValueError,KeyError,TypeError): pass
        style = ttk.Style(self)
        style.theme_use('clam')
        self.configure(background='#f5f6fa')
        style.configure('TFrame', background='#f5f6fa')
        style.configure('TLabel', background='#f5f6fa', foreground='#182234', font=('Segoe UI', 10))
        style.configure('Muted.TLabel', foreground='#586579')
        style.configure('TButton', font=('Segoe UI', 10), padding=(12, 8), background='#e9edf3', borderwidth=1)
        style.map('TButton', background=[('active', '#dde5f0')])
        style.configure('Primary.TButton', background='#2459a9', foreground='white')
        style.map('Primary.TButton', background=[('disabled', '#dce3ed'), ('active', '#194781')], foreground=[('disabled', '#738097'), ('!disabled', 'white')])
        style.configure('TEntry', padding=7, font=('Segoe UI', 10))
        style.configure('Treeview', rowheight=32, font=('Segoe UI', 10), background='white', fieldbackground='white', borderwidth=0)
        style.configure('Media.Treeview',rowheight=64,indent=0)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), background='#e9edf3', padding=(8, 9))
        body = ttk.Frame(self, padding=24)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)
        header = ttk.Frame(body)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 20))
        ttk.Label(header, text='Sortrr', font=('Segoe UI', 26, 'bold')).pack(anchor='w')
        ttk.Label(header, text='A tidy library. Ready for Plex, Jellyfin, and Emby.', style='Muted.TLabel').pack(anchor='w', pady=(3, 0))
        folders = ttk.Frame(body)
        folders.grid(row=1, column=0, sticky='ew')
        folders.columnconfigure(1, weight=1)
        self.folder_controls=[]
        for index, (label, var) in enumerate([('Media folder', self.source), ('Library destination', self.library)]):
            ttk.Label(folders, text=label, width=19).grid(row=index, column=0, sticky='w', pady=5)
            entry=ttk.Entry(folders, textvariable=var, font=('Segoe UI', 10))
            entry.grid(row=index, column=1, sticky='ew', pady=5)
            browse=ttk.Button(folders, text='Browse...', command=lambda v=var: self.browse(v))
            browse.grid(row=index, column=2, padx=(10, 0), pady=5)
            self.folder_controls.extend([entry,browse])
        self.mode_control=ttk.Checkbutton(folders, text='Move in place (organize inside the media folder; no duplicate copies)', variable=self.in_place, command=self.update_mode)
        self.mode_control.grid(row=2,column=0,columnspan=3,sticky='w',pady=(8,0))
        automatic=ttk.Frame(folders); automatic.grid(row=3,column=0,columnspan=3,sticky='w',pady=(6,0))
        rename_box=ttk.Checkbutton(automatic,text='Rename sorted files using preset',variable=self.auto_rename,command=self.automatic_changed)
        rename_box.pack(side='left',padx=(0,18))
        cleanup_box=ttk.Checkbutton(automatic,text='Clean source folders after sorting',variable=self.auto_cleanup,command=self.automatic_changed)
        cleanup_box.pack(side='left')
        self.automatic_controls=[rename_box,cleanup_box]
        self.buttons = []
        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky='ew', pady=(16, 8))
        for text, action in [('1. Scan & identify', self.scan), ('2. Organize ready files', self.copy)]:
            button = ttk.Button(actions, text=text, command=action, style='Primary.TButton')
            button.pack(side='left', padx=(0, 10))
            self.buttons.append(button)
        settings = ttk.Button(actions, text='Movie database...', command=self.database)
        settings.pack(side='right')
        self.buttons.append(settings)
        sorting=ttk.Button(actions,text='Folder layouts...',command=self.sorting_options)
        sorting.pack(side='right',padx=(0,8)); self.buttons.append(sorting)
        tools = ttk.Frame(body)
        tools.grid(row=3, column=0, sticky='ew', pady=(0, 12))
        toolbuttons=ttk.Frame(tools); toolbuttons.pack(side='top',fill='x')
        for index,(text,action) in enumerate([('Review selected',self.review),('Skip selected',self.skip),('Re-identify selected',self.reidentify_selected),('Rename selected...',self.rename_selected),('Clean source folders...',self.cleanup_source),('Undo last operation',self.undo),('Clear cache...',self.clear_cache),('Resolve unmatched...',self.resolve_wizard)]):
            button=ttk.Button(toolbuttons,text=text,command=action)
            button.grid(row=index//4,column=index%4,sticky='w',padx=(0,8),pady=(0,4))
            self.buttons.append(button)
        viewbar=ttk.Frame(tools); viewbar.pack(side='top',fill='x',pady=(10,0))
        ttk.Label(viewbar,text='Show').pack(side='left',padx=(0,6))
        filter_box=ttk.Combobox(viewbar,textvariable=self.filter_var,values=('All media','Movies','TV shows'),state='readonly',width=12)
        filter_box.pack(side='left',padx=(0,18)); filter_box.bind('<<ComboboxSelected>>',self.view_changed)
        ttk.Label(viewbar,text='Sort by').pack(side='left',padx=(0,6))
        sort_box=ttk.Combobox(viewbar,textvariable=self.sort_var,values=list(VIEW_SORT_FIELDS),state='readonly',width=13)
        sort_box.pack(side='left',padx=(0,12)); sort_box.bind('<<ComboboxSelected>>',self.view_changed)
        ttk.Checkbutton(viewbar,text='Descending',variable=self.descending,command=self.view_changed).pack(side='left')
        self.visible_count=tk.StringVar(value='0 files')
        ttk.Label(viewbar,textvariable=self.visible_count,style='Muted.TLabel').pack(side='right')
        table = ttk.Frame(body)
        table.grid(row=4, column=0, sticky='nsew')
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=('file','match','status','kind','year','season','episode'),displaycolumns=('file','match','kind','year','season','episode','status'), show='tree headings', selectmode='extended',style='Media.Treeview')
        self.tree.heading('#0',text='Preview'); self.tree.column('#0',width=108,minwidth=108,stretch=False)
        self.thumbnail_placeholder=tk.PhotoImage(width=96,height=54)
        self.thumbnail_placeholder.put('#e4e8ef',to=(0,0,96,54))
        for y in range(16,39):
            span=11-abs(27-y)
            if span>0: self.thumbnail_placeholder.put('#7c899b',to=(40,y,40+span,y+1))
        self.column_labels={'file':'Source file','match':'Title','kind':'Type','year':'Year','season':'Season','episode':'Episode','status':'Status'}
        for col,width in [('file',250),('match',220),('kind',70),('year',70),('season',80),('episode',85),('status',220)]:
            self.tree.heading(col,text=self.column_labels[col],anchor='w',command=lambda field=col:self.sort_column(field))
            self.tree.column(col,width=width,minwidth=55 if col in ('year','season','episode','kind') else 120,anchor='w')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.scroll_media)
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.hover_preview=HoverScrubber(self,self.tree,self.previews,lambda row:self.current_path(self.items[int(row)]))
        for event in ('<Configure>','<MouseWheel>','<KeyRelease>'):
            self.tree.bind(event,lambda event:self.schedule_thumbnails(),add='+')
        self.tree.bind('<Double-1>', lambda e: self.review())
        self.tree.bind('<<TreeviewSelect>>', self.preview)
        footer = ttk.Frame(body)
        footer.grid(row=5, column=0, sticky='ew', pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        self.detail = tk.StringVar(value='Select a row to preview its destination. Double-click to correct a match.')
        detail = ttk.Label(footer, textvariable=self.detail, style='Muted.TLabel')
        detail.grid(row=0, column=0, sticky='ew')
        self.safety_text=tk.StringVar()
        safety = ttk.Label(footer, textvariable=self.safety_text, style='Muted.TLabel')
        safety.grid(row=1, column=0, sticky='ew', pady=(5, 0))
        status = ttk.Label(footer, textvariable=self.status)
        status.grid(row=2, column=0, sticky='ew', pady=(9, 0))
        self.progress = ttk.Progressbar(footer, mode='indeterminate')
        self.progress.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        def wrap_footer(event):
            for label in (detail, safety, status):
                label.configure(wraplength=max(200, event.width))
        footer.bind('<Configure>', wrap_footer)
        if not os.environ.get('SORTRR_TMDB_TOKEN','').strip():
            self.status.set('Connect TMDb using Movie database to identify movies. TV uses TVmaze.')
        self.update_mode()
        self.after(100,self.pump); self.protocol('WM_DELETE_WINDOW',self.close)
    def scroll_media(self,*args):
        self.tree.yview(*args); self.schedule_thumbnails(); self.hover_preview.hide()
    def schedule_thumbnails(self):
        if self.thumbnail_timer is None: self.thumbnail_timer=self.after(100,self.load_visible_thumbnails)
    def load_visible_thumbnails(self):
        self.thumbnail_timer=None
        if self.previews.closed or not self.previews.available: return
        rows={self.tree.identify_row(y) for y in range(25,max(26,self.tree.winfo_height()),24)}
        for row in rows:
            if not row: continue
            index=int(row)
            if index>=len(self.items): continue
            media=self.items[index]; path=self.current_path(media)
            try: _,identity=self.previews.identity(path)
            except (OSError,ValueError): continue
            if self.thumbnail_keys.get(row)==identity or (row,identity) in self.thumbnail_pending: continue
            pending=(row,identity); self.thumbnail_pending.add(pending)
            def done(frame,error,row=row,identity=identity,media=media,pending=pending):
                self.thumbnail_pending.discard(pending)
                if not self.tree.winfo_exists() or int(row)>=len(self.items) or self.items[int(row)] is not media: return
                self.thumbnail_keys[row]=identity
                if frame:
                    try:
                        self.thumbnail_images[row]=tk.PhotoImage(file=str(frame.path))
                        self.tree.item(row,image=self.thumbnail_images[row])
                    except (tk.TclError,OSError): self.thumbnail_keys.pop(row,None)
            if not self.previews.request(path,done,size=(96,54),fraction=.1):
                self.thumbnail_pending.discard(pending); self.schedule_thumbnails()
    def save_settings(self):
        DATA.mkdir(exist_ok=True)
        config={'source':self.source.get(),'library':self.library.get(),'in_place':self.in_place.get(),'sorting':self.options.to_dict(),'media_filter':self.filter_var.get(),'sort_by':self.sort_var.get(),'descending':self.descending.get(),'auto_cleanup':self.auto_cleanup.get()}
        (DATA/'settings.json').write_text(json.dumps(config),encoding='utf-8')
    def automatic_changed(self):
        self.apply_options(replace(self.options,rename_files=self.auto_rename.get()))
    def schedule_view(self):
        if self.view_timer is None: self.view_timer=self.after(75,self.apply_view)
    def apply_view(self):
        if self.view_timer is not None:
            self.after_cancel(self.view_timer); self.view_timer=None
        field=VIEW_SORT_FIELDS[self.sort_var.get()]
        order=sorted_media_indices(self.items,field,self.descending.get(),self.filter_var.get())
        visible={str(i) for i in order}
        hidden=[i for i in self.tree.get_children() if i not in visible]
        for i in hidden: self.tree.detach(i)
        if hidden: self.tree.selection_remove(*hidden)
        for i in order:
            if self.tree.exists(str(i)): self.tree.move(str(i),'','end')
        self.visible_count.set(f'{len(order)} of {len(self.items)} files')
        self.schedule_thumbnails()
        for column,label in self.column_labels.items():
            suffix=(' '+chr(8595 if self.descending.get() else 8593)) if column==field else ''
            self.tree.heading(column,text=label+suffix)
    def view_changed(self,event=None):
        self.apply_view(); self.save_settings()
    def sort_column(self,field):
        name=next(label for label,value in VIEW_SORT_FIELDS.items() if value==field)
        self.descending.set(not self.descending.get() if self.sort_var.get()==name else False)
        self.sort_var.set(name); self.view_changed()
    def apply_options(self,options):
        history=History()
        for m in self.items:
            if m.status in {'Moved','Renamed'}:
                m.source=self.current_path(m)
                if m.source.exists():
                    st=m.source.stat(); m.signature=(st.st_size,st.st_mtime_ns)
        self.options=options; self.auto_rename.set(options.rename_files)
        for m in self.items:
            if not m.chosen or m.status not in ('Ready','Copied','Moved','Renamed','Already organized','Previously copied','Previously moved'): continue
            if not m.source.is_file(): m.status='File unavailable; scan again'; continue
            target=destination(m,self.output_folder(),options)
            if History.key(m.source)==History.key(target): m.status='Already organized'
            elif history.processed(m,self.output_folder(),'move' if self.in_place.get() else 'copy',options):
                m.status='Previously moved' if self.in_place.get() else 'Previously copied'
            else: m.status='Ready'
        self.save_settings(); self.refresh(); self.preview()
    def sorting_options(self):
        if self.busy: return
        win=tk.Toplevel(self); win.title('Folder layouts and server presets'); win.geometry('780x720'); win.minsize(730,700)
        win.transient(self); win.grab_set()
        body=ttk.Frame(win,padding=22); body.pack(fill='both',expand=True); body.columnconfigure(0,weight=1)
        preset=tk.StringVar(value=preset_name(self.options))
        movie=tk.StringVar(value=next(k for k,v in MOVIE_LAYOUTS.items() if v==self.options.movie_layout))
        show=tk.StringVar(value=next(k for k,v in SHOW_LAYOUTS.items() if v==self.options.show_layout))
        ids=tk.StringVar(value=next(k for k,v in ID_STYLES.items() if v==self.options.id_style))
        ttk.Label(body,text='Media server preset',font=('Segoe UI',11,'bold')).grid(row=0,column=0,sticky='w')
        presets=ttk.Combobox(body,textvariable=preset,values=list(LAYOUT_PRESETS)+['Custom'],state='readonly')
        presets.grid(row=1,column=0,sticky='ew',pady=(6,8))
        description=ttk.Label(body,wraplength=720,style='Muted.TLabel'); description.grid(row=2,column=0,sticky='ew')
        guides=ttk.Frame(body); guides.grid(row=3,column=0,sticky='ew',pady=(6,14))
        ttk.Label(body,text='Movie folders',font=('Segoe UI',11,'bold')).grid(row=4,column=0,sticky='w')
        movies=ttk.Combobox(body,textvariable=movie,values=list(MOVIE_LAYOUTS),state='readonly')
        movies.grid(row=5,column=0,sticky='ew',pady=(6,8))
        movie_example=ttk.Label(body,wraplength=720,style='Muted.TLabel'); movie_example.grid(row=6,column=0,sticky='ew')
        ttk.Label(body,text='TV show folders',font=('Segoe UI',11,'bold')).grid(row=7,column=0,sticky='w',pady=(14,0))
        shows=ttk.Combobox(body,textvariable=show,values=list(SHOW_LAYOUTS),state='readonly')
        shows.grid(row=8,column=0,sticky='ew',pady=(6,8))
        show_example=ttk.Label(body,wraplength=720,style='Muted.TLabel'); show_example.grid(row=9,column=0,sticky='ew')
        ttk.Label(body,text='Database ID tags',font=('Segoe UI',11,'bold')).grid(row=10,column=0,sticky='w',pady=(14,0))
        id_box=ttk.Combobox(body,textvariable=ids,values=list(ID_STYLES),state='readonly')
        id_box.grid(row=11,column=0,sticky='ew',pady=(6,8))
        ttk.Label(body,text='Only verified provider IDs are added. If unavailable, the ID tag is omitted. Point your server libraries at Movies and TV Shows.',wraplength=720,style='Muted.TLabel').grid(row=12,column=0,sticky='ew')
        ttk.Label(body,text='Applying a preset updates previews. Files move only when you choose Organize.',wraplength=720,style='Muted.TLabel').grid(row=13,column=0,sticky='ew',pady=(12,10))
        actions=ttk.Frame(body); actions.grid(row=14,column=0,sticky='ew')
        def chosen(): return SortOptions(MOVIE_LAYOUTS[movie.get()],SHOW_LAYOUTS[show.get()],ID_STYLES[ids.get()],self.auto_rename.get())
        def examples():
            film=Media(Path('Example.mkv'),'Example Movie',chosen={'title':'Example Movie','year':'2020','provider':'TMDB','id':12345})
            series=Media(Path('Example.mkv'),'Example Show',season=2,episode=3,chosen={'title':'Example Show','year':'2018','provider':'TVmaze','id':678,'external_ids':{'thetvdb':54321}})
            movie_example.configure(text=str(destination(film,Path('Library'),chosen())))
            show_example.configure(text=str(destination(series,Path('Library'),chosen())))
        def describe():
            for widget in guides.winfo_children(): widget.destroy()
            selected=LAYOUT_PRESETS.get(preset.get())
            description.configure(text=selected.description if selected else 'Custom layout. Choose a server preset above to restore its documented folder structure.')
            if selected:
                for index,(label,url) in enumerate(selected.docs):
                    ttk.Button(guides,text=label+' guide',command=lambda link=url:webbrowser.open(link)).grid(row=index//3,column=index%3,sticky='w',padx=(0,6),pady=2)
        def preset_selected(event=None):
            selected=LAYOUT_PRESETS.get(preset.get())
            if selected:
                movie.set(next(k for k,v in MOVIE_LAYOUTS.items() if v==selected.options.movie_layout))
                show.set(next(k for k,v in SHOW_LAYOUTS.items() if v==selected.options.show_layout))
                ids.set(next(k for k,v in ID_STYLES.items() if v==selected.options.id_style))
            describe(); examples()
        def custom_changed(event=None): preset.set('Custom'); describe(); examples()
        presets.bind('<<ComboboxSelected>>',preset_selected)
        for box in (movies,shows,id_box): box.bind('<<ComboboxSelected>>',custom_changed)
        describe(); examples()
        def wrap_dialog(event):
            for widget in body.winfo_children():
                if isinstance(widget,ttk.Label): widget.configure(wraplength=max(200,event.width-44))
        body.bind('<Configure>',wrap_dialog)
        def apply(): self.apply_options(chosen()); win.destroy()
        ttk.Button(actions,text='Apply layouts',command=apply,style='Primary.TButton').pack(side='right')
        ttk.Button(actions,text='Cancel',command=win.destroy).pack(side='right',padx=8)
    def output_folder(self):
        return self.source.get() if self.in_place.get() else self.library.get()
    def update_mode(self):
        in_place=self.in_place.get()
        for widget in self.folder_controls[2:]:
            widget.state(['disabled'] if in_place else ['!disabled'])
        self.safety_text.set('Move mode: files are relocated within the media folder. Undo can restore them.' if in_place else 'Copy mode: originals preserved. Existing files never overwritten.')
        self.preview()
    def database(self):
        token=simpledialog.askstring('Connect TMDb - default movie database','Paste your TMDb API Read Access Token (not your password).\nGet one at https://www.themoviedb.org/settings/api\nTV uses TVmaze and needs no token.\nSaved locally in data/tmdb-token.txt (plain text).\nLeave blank to disconnect TMDb.',show='*',parent=self)

        if token is None: return
        token=token.strip(); DATA.mkdir(exist_ok=True)
        (DATA/'tmdb-token.txt').write_text(token,encoding='utf-8')
        if token: os.environ['SORTRR_TMDB_TOKEN']=token
        else: os.environ.pop('SORTRR_TMDB_TOKEN',None)
        self.catalog=Catalog(); self.status.set('TMDb connection saved. Scan again to identify movies.' if token else 'TMDb disconnected. Connect it before identifying movies.')
    def browse(self,var):
        if self.busy: return
        value=filedialog.askdirectory()
        if value: var.set(value)
    def run(self,task):
        if self.busy: return
        self.busy=True; self.progress.start()
        for b in self.buttons + self.folder_controls + self.automatic_controls + [self.mode_control]: b.state(['disabled'])
        def worker():
            try: task()
            except Exception as ex: self.events.put(('error',str(ex)))
            finally: self.events.put(('done',None))
        threading.Thread(target=worker,daemon=True).start()
    def pump(self):
        try:
            for _ in range(200):
                event,value=self.events.get_nowait()
                if event=='status': self.status.set(value)
                elif event=='media':
                    self.items.append(value)
                    self.update_row(len(self.items)-1)
                elif event=='row': self.update_row(value)
                elif event=='refresh': self.refresh()
                elif event=='callback': value()
                elif event=='file_dialog': self.pending_file_dialog=value
                elif event=='cleanup_report':
                    if value['skipped']: messagebox.showinfo('Cleanup completed with skipped items','\n'.join(value['skipped'][:5])+'\n\nFull details are saved in the operation journal.')
                elif event=='database_needed': self.database_needed=True
                elif event=='error': messagebox.showerror('Sortrr',value)
                elif event=='done':
                    self.busy=False; self.progress.stop()
                    if self.previews.closed:
                        self.thumbnail_pending.clear()
                        self.previews=PreviewManager(DATA/'previews',lambda callback:self.events.put(('callback',callback)))
                        self.hover_preview.manager=self.previews
                    self.refresh()
                    for b in self.buttons + self.folder_controls + self.automatic_controls + [self.mode_control]: b.state(['!disabled'])
                    self.update_mode()
                    if self.database_needed:
                        self.database_needed=False
                        self.database()
                    if self.pending_file_dialog:
                        dialog=self.pending_file_dialog; self.pending_file_dialog=None
                        if dialog[0]=='rename': self.show_rename_preview(dialog[1],dialog[2])
                        else: self.show_cleanup_preview(dialog[1])
                elif event=='review':
                    m, candidates = value
                    m.candidates = candidates
                    self.show_review(m)
        except queue.Empty: pass
        self.after(100,self.pump)
    def update_row(self, i):
        m=self.items[i]; c=m.chosen
        values=(m.source.name,f"{c['title']} ({c['year']})" if c else '-',m.status + (' (remembered)' if m.cached else ''),m.kind,c.get('year','') if c else m.year,m.season if m.season is not None else '-',m.episode if m.episode is not None else '-')
        if self.tree.exists(str(i)): self.tree.item(str(i),values=values)
        else: self.tree.insert('', 'end',iid=str(i),values=values,image=self.thumbnail_placeholder)
        self.schedule_view()
    def refresh(self):
        for i in range(len(self.items)): self.update_row(i)
    def scan(self):
        src=Path(self.source.get()).expanduser(); dst=Path(self.output_folder()).expanduser()
        if not self.source.get() or not src.is_dir() or not self.output_folder(): messagebox.showerror('Folders needed','Choose an existing media folder and a library destination.'); return
        src=src.resolve(); dst=dst.resolve()
        if not self.in_place.get() and (src==dst or src.is_relative_to(dst)): messagebox.showerror('Choose separate folders','The media folder cannot be inside the destination library.'); return
        self.save_settings()
        if self.view_timer is not None:
            self.after_cancel(self.view_timer); self.view_timer=None
        old_ids=[str(i) for i in range(len(self.items)) if self.tree.exists(str(i))]
        if old_ids: self.tree.delete(*old_ids)
        self.items=[]; self.visible_count.set('0 files')
        self.thumbnail_keys.clear(); self.thumbnail_images.clear(); self.thumbnail_pending.clear(); self.hover_preview.hide()
        in_place=self.in_place.get(); options=self.options
        def task():
            history=History(); found=[]; discovery_errors=0
            def discover():
                nonlocal discovery_errors
                for folder,dirs,files in os.walk(src,followlinks=False):
                    dirs[:]=[d for d in dirs if d.casefold()!='.sortrr-trash' and not (Path(folder)/d).is_symlink() and (in_place or not (Path(folder)/d).resolve().is_relative_to(dst))]
                    for name in sorted(files):
                        p=Path(folder)/name
                        if p.suffix.lower() not in VIDEO or p.is_symlink(): continue
                        try: m=parse(p)
                        except OSError:
                            discovery_errors+=1; continue
                        index=len(found); found.append(m)
                        if m.status=='Waiting': m.status='Identifying'
                        self.events.put(('media',m))
                        yield index,m
            def completed(index,m):
                self.events.put(('row',index))
                self.events.put(('status',f'Identified: {m.source.name} - {m.status}'))
            result=identify_batch(discover(),self.catalog,history,dst,'move' if in_place else 'copy',report=completed,options=options)
            if result['setup']:
                self.events.put(('status',result['setup']))
                self.events.put(('database_needed',None))
            else:
                self.events.put(('status',f"Scan complete: {len(found)} files, {sum(m.status=='Ready' for m in found)} ready, {result['remembered']} remembered, {result['errors']+discovery_errors} errors. Review uncertain matches, then organize."))
        self.run(task)
    def selected(self): return [self.items[int(i)] for i in self.tree.selection()]
    def preview(self,event=None):
        ms=self.selected()
        if ms:
            m=ms[0]; self.detail.set(str(destination(m,self.output_folder(),self.options)) if m.chosen else f'{m.source} | {m.kind} | Search: {m.query}')
    def skip(self):
        for m in self.selected():
            m.chosen=None; m.status='Skipped by you'; History().save(m)
        self.refresh()
    def current_path(self,m):
        # A row may still refer to the original path immediately after an in-place move.
        if m.status in {'Moved','Renamed'} and m.chosen:
            target=m.organized_path or destination(m,self.output_folder(),self.options)
            if target.is_file(): return target
        return m.source
    def wrap_labels(self,frame,width):
        for widget in frame.winfo_children():
            if isinstance(widget,ttk.Label): widget.configure(wraplength=max(200,width))
    def rename_selected(self):
        if self.busy: return
        items=[m for m in self.selected() if m.chosen]
        if not items:
            self.status.set('Select identified files to preview their new names.')
            return
        for m in items: m.source=self.current_path(m)
        options=self.options
        def task(): self.events.put(('file_dialog',('rename',items,plan_renames(items,options))))
        self.run(task)
    def show_rename_preview(self,items,changes):
        win=tk.Toplevel(self); win.title('Rename selected files'); win.geometry('900x510'); win.minsize(760,460); win.transient(self); win.grab_set()
        body=ttk.Frame(win,padding=20); body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1); body.rowconfigure(2,weight=1)
        body.bind('<Configure>',lambda event:self.wrap_labels(body,event.width-40))
        ttk.Label(body,text='Rename media and matching subtitles in their current folders.',font=('Segoe UI',11,'bold')).grid(row=0,column=0,sticky='ew')
        ttk.Label(body,text='Names follow your selected server preset. Existing files are never overwritten.',style='Muted.TLabel').grid(row=1,column=0,sticky='ew',pady=(5,12))
        table=ttk.Frame(body); table.grid(row=2,column=0,sticky='nsew'); table.columnconfigure(0,weight=1); table.rowconfigure(0,weight=1)
        tree=ttk.Treeview(table,columns=('old','new','status'),show='headings')
        for field,title,width in [('old','Current name',270),('new','New name',330),('status','Status',200)]:
            tree.heading(field,text=title); tree.column(field,width=width,minwidth=100)
        tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(table,orient='vertical',command=tree.yview); scroll.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(table,orient='horizontal',command=tree.xview); horizontal.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
        for change in changes: tree.insert('','end',values=(change.source.name,change.target.name,change.error or 'Ready'))
        ttk.Label(body,text='Review names above. Undo last operation can restore the original names.',style='Muted.TLabel').grid(row=3,column=0,sticky='ew',pady=10)
        bar=ttk.Frame(body); bar.grid(row=4,column=0,sticky='ew')
        options=self.options; library=self.output_folder() or self.source.get()
        def apply():
            win.destroy()
            for m in items: m.status='Ready'
            def task():
                self.previews.close(wait=True)
                count,journal=organize(items,library,lambda status:self.events.put(('refresh',None)),mode='rename',options=options)
                if count: self.journal=journal
                self.events.put(('status',f'Renamed {count} of {len(items)} media files and matching subtitles. Review row statuses for skipped files.'))
            self.run(task)
        button=ttk.Button(bar,text='Rename files',command=apply,style='Primary.TButton'); button.pack(side='right')
        if not any(not change.error for change in changes): button.state(['disabled'])
        ttk.Button(bar,text='Cancel',command=win.destroy).pack(side='right',padx=8)
    def cleanup_source(self):
        if self.busy: return
        if not self.source.get() or not Path(self.source.get()).is_dir():
            self.status.set('Choose an existing media folder before previewing cleanup.'); return
        root=Path(self.source.get()).resolve(); output=Path(self.output_folder()).resolve() if self.output_folder() else None
        excluded=[output] if output and output!=root else [root/'Movies',root/'TV Shows']
        def task(): self.events.put(('file_dialog',('cleanup',plan_cleanup(root,excluded))))
        self.run(task)
    def show_cleanup_preview(self,plan):
        win=tk.Toplevel(self); win.title('Clean source folders'); win.geometry('900x640'); win.minsize(800,580); win.transient(self); win.grab_set()
        body=ttk.Frame(win,padding=20); body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1); body.rowconfigure(4,weight=1)
        body.bind('<Configure>',lambda event:self.wrap_labels(body,event.width-40))
        ttk.Label(body,text='Review source-folder cleanup',font=('Segoe UI',13,'bold')).grid(row=0,column=0,sticky='ew')
        ttk.Label(body,text='Files go to .sortrr-trash inside the source folder so Undo can restore them. This does not free disk space.',wraplength=850,style='Muted.TLabel').grid(row=1,column=0,sticky='ew',pady=(5,4))
        ttk.Label(body,text='Only system junk and checksums are preselected. Notes, archives, samples, metadata and artwork require selection.',wraplength=850,style='Muted.TLabel').grid(row=2,column=0,sticky='ew',pady=(0,8))
        tools=ttk.Frame(body); tools.grid(row=3,column=0,sticky='ew',pady=(0,8))
        selected={item.path for item in plan.files if item.recommended}; remove_empty=tk.BooleanVar(value=True)
        summary=tk.StringVar()
        table=ttk.Frame(body); table.grid(row=4,column=0,sticky='nsew'); table.columnconfigure(0,weight=1); table.rowconfigure(0,weight=1)
        tree=ttk.Treeview(table,columns=('remove','path','reason','size'),show='headings',selectmode='extended')
        for field,title,width in [('remove','Remove',65),('path','Source-relative path',390),('reason','Category',230),('size','Size',100)]:
            tree.heading(field,text=title); tree.column(field,width=width,minwidth=55)
        tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(table,orient='vertical',command=tree.yview); scroll.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(table,orient='horizontal',command=tree.xview); horizontal.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
        def refresh():
            tree.delete(*tree.get_children())
            for i,item in enumerate(plan.files):
                tree.insert('','end',iid='f'+str(i),values=('[x]' if item.path in selected else '[ ]',str(item.path.relative_to(plan.root)),item.category,f'{item.signature[0]:,} B'))
            folders=cleanup_empty_folders(plan,selected) if remove_empty.get() else []
            for i,folder in enumerate(folders): tree.insert('','end',iid='d'+str(i),values=('[x]',str(folder.relative_to(plan.root)),'Empty folder',''))
            summary.set(f'{len(selected)} files and {len(folders)} empty folders selected. Double-click files or press Space to toggle.')
            apply_button.state(['!disabled'] if selected or folders else ['disabled'])
        def choose(which):
            selected.clear()
            selected.update(item.path for item in plan.files if which=='all' or (which=='recommended' and item.recommended))
            refresh()
        for label,which in [('Recommended only','recommended'),('Select all files','all'),('Clear file selection','none')]:
            ttk.Button(tools,text=label,command=lambda choice=which:choose(choice)).pack(side='left',padx=(0,8))
        ttk.Checkbutton(tools,text='Remove empty folders',variable=remove_empty,command=refresh).pack(side='left')
        def toggle(event):
            ids=[tree.identify_row(event.y)] if event.type==tk.EventType.ButtonPress else list(tree.selection())
            for key in ids:
                if key.startswith('f'):
                    path=plan.files[int(key[1:])].path
                    if path in selected: selected.remove(path)
                    else: selected.add(path)
            refresh(); return 'break'
        tree.bind('<Double-1>',toggle); tree.bind('<space>',toggle)
        ttk.Label(body,textvariable=summary,wraplength=850).grid(row=5,column=0,sticky='ew',pady=10)
        bar=ttk.Frame(body); bar.grid(row=6,column=0,sticky='ew')
        def apply():
            chosen=set(selected); empty=remove_empty.get(); win.destroy()
            def task():
                self.previews.close(wait=True)
                result,journal=apply_cleanup(plan,chosen,empty,lambda text:self.events.put(('status',text)))
                if result['files'] or result['folders']: self.journal=journal
                self.events.put(('status',f"Cleanup complete: {result['files']} files stored for recovery, {result['folders']} empty folders removed, {len(result['skipped'])} skipped."))
                self.events.put(('cleanup_report',result))
            self.run(task)
        apply_button=ttk.Button(bar,text='Clean reviewed items',command=apply,style='Primary.TButton'); apply_button.pack(side='right')
        ttk.Button(bar,text='Cancel',command=win.destroy).pack(side='right',padx=8)
        refresh()
    def reidentify_selected(self):
        if self.busy: return
        selected=[int(i) for i in self.tree.selection()]
        if not selected:
            self.status.set('Select one or more files to re-identify.')
            return
        for i in selected:
            m=self.items[i]; m.source=self.current_path(m)
            m.chosen=None; m.candidates=[]; m.cached=False; m.status='Re-identifying'
            self.update_row(i)
        self.preview()
        def task():
            result=identify_batch([(i,self.items[i]) for i in selected],self.catalog,reidentify=True,report=lambda i,m:self.events.put(('row',i)))
            if result['setup']:
                self.events.put(('status',result['setup']))
                self.events.put(('database_needed',None))
            else:
                self.events.put(('status',f"Re-identification complete: {len(selected)} files, {result['errors']} errors. Review results before organizing."))
        self.run(task)
    def clear_cache(self):
        if self.busy: return
        if not messagebox.askyesno('Clear cache', 'Forget all saved matches, skips, processed-file history, and cached database responses?\n\nMedia, settings, database credentials, and undo records are preserved. Scan again afterward to identify files.'):
            return
        paths=[self.current_path(m) for m in self.items]
        def task():
            History().clear()
            self.catalog.clear_cache()
            for m,path in zip(self.items,paths):
                m.source=path; m.chosen=None; m.candidates=[]; m.cached=False; m.status='Not identified'
            self.events.put(('refresh',None))
            self.events.put(('status','Cache cleared. Scan again to identify files.'))
        self.run(task)
    def review(self):
        if self.busy: return
        ms=self.selected()
        if not ms: return
        if ms[0].status.startswith('Unsupported'): messagebox.showinfo('Unsupported naming','Multi-episode and date-based files are held for safety. Rename to a single S01E01 episode before rescanning.'); return
        self.show_review(ms[0])
    def resolve_wizard(self):
        if self.busy: return
        visible=sorted_media_indices(self.items,VIEW_SORT_FIELDS[self.sort_var.get()],self.descending.get(),self.filter_var.get())
        items=unresolved_media([self.items[i] for i in visible])
        if not items:
            self.status.set('No unresolved files in this view. Scan first, or change the media filter.')
            return
        self.hover_preview.hide()
        win=tk.Toplevel(self); win.title('Resolve unmatched files'); win.geometry('1180x720'); win.minsize(1060,650); win.transient(self); win.grab_set()
        body=ttk.Frame(win,padding=20); body.pack(fill='both',expand=True); body.columnconfigure(0,weight=1); body.columnconfigure(1,minsize=370); body.rowconfigure(4,weight=1)
        body.bind('<Configure>',lambda event:self.wrap_labels(body,event.width-430))
        sidebar=ttk.Frame(body); sidebar.grid(row=0,column=1,rowspan=6,sticky='nsew',padx=(16,0)); sidebar.columnconfigure(0,weight=1); sidebar.rowconfigure(1,weight=1)
        viewer=VideoPreview(sidebar,self.previews); viewer.grid(row=0,column=0,sticky='new')
        details_panel=ttk.Frame(sidebar,padding=(12,0,0,0)); details_panel.grid(row=1,column=0,sticky='nsew'); details_panel.columnconfigure(0,weight=1); details_panel.rowconfigure(1,weight=1)
        details_title=tk.StringVar(value='Database entry information')
        ttk.Label(details_panel,textvariable=details_title,font=('Segoe UI',10,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,5))
        details_text=tk.Text(details_panel,width=38,height=7,wrap='word',font=('Segoe UI',9),background='#f5f6fa',foreground='#182234',relief='flat',state='disabled')
        details_text.grid(row=1,column=0,sticky='nsew')
        details_scroll=ttk.Scrollbar(details_panel,orient='vertical',command=details_text.yview); details_scroll.grid(row=1,column=1,sticky='ns'); details_text.configure(yscrollcommand=details_scroll.set)
        entry_link=ttk.Button(details_panel,text='Open database entry'); entry_link.grid(row=2,column=0,columnspan=2,sticky='w',pady=(5,0))
        detail_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='sortrr-entry')
        detail_state={'generation':0,'timer':None,'future':None,'url':''}
        def set_details(text):
            details_text.configure(state='normal'); details_text.delete('1.0','end'); details_text.insert('1.0',text); details_text.configure(state='disabled')
        def open_entry():
            if detail_state['url']: webbrowser.open(detail_state['url'])
        entry_link.configure(command=open_entry)
        def detail_selected(event=None):
            detail_state['generation']+=1; generation=detail_state['generation']
            if detail_state['timer']: win.after_cancel(detail_state['timer']); detail_state['timer']=None
            if detail_state['future']: detail_state['future'].cancel()
            detail_state['url']=''; entry_link.state(['disabled'])
            selected=matches.selection()
            if not selected or int(selected[0])>=len(state['results']):
                details_title.set('Database entry information'); set_details('Select a search result to see its description and details.'); return
            candidate=dict(state['results'][int(selected[0])]); media_kind=kind.get()
            details_title.set(candidate.get('provider','Database')+' entry')
            set_details(entry_info_text(candidate)+'\n\nLoading full details...')
            def fetch():
                detail_state['timer']=None
                def task():
                    try: data,error=self.catalog.entry_details(candidate,media_kind),None
                    except Exception as exc: data,error=None,str(exc)
                    def done():
                        if not win.winfo_exists() or generation!=detail_state['generation']: return
                        if error:
                            set_details(entry_info_text(candidate)+'\n\nDetails unavailable: '+error); return
                        details_title.set(data.get('provider','Database')+' entry')
                        set_details(entry_info_text(data)); detail_state['url']=data.get('entry_url','')
                        entry_link.state(['!disabled'] if detail_state['url'] else ['disabled'])
                    self.events.put(('callback',done))
                detail_state['future']=detail_pool.submit(task)
            detail_state['timer']=win.after(180,fetch)
        def close_details(event):
            if event.widget!=win: return
            detail_state['generation']+=1
            if detail_state['timer']: win.after_cancel(detail_state['timer'])
            detail_pool.shutdown(wait=False,cancel_futures=True)
        win.bind('<Destroy>',close_details,add='+')
        progress=tk.StringVar(); filename=tk.StringVar(); notice=tk.StringVar()
        ttk.Label(body,textvariable=progress,font=('Segoe UI',13,'bold')).grid(row=0,column=0,sticky='ew')
        ttk.Label(body,textvariable=filename,style='Muted.TLabel',wraplength=810).grid(row=1,column=0,sticky='ew',pady=(5,10))
        form=ttk.Frame(body); form.grid(row=2,column=0,sticky='ew'); form.columnconfigure(1,weight=1)
        query=tk.StringVar(); year=tk.StringVar(); kind=tk.StringVar(); season=tk.StringVar(); episode=tk.StringVar()
        ttk.Label(form,text='Title').grid(row=0,column=0,sticky='w',padx=(0,10))
        title_entry=ttk.Entry(form,textvariable=query); title_entry.grid(row=0,column=1,sticky='ew')
        search_button=ttk.Button(form,text='Search'); search_button.grid(row=0,column=2,padx=(10,0))
        fields=ttk.Frame(form); fields.grid(row=1,column=0,columnspan=3,sticky='ew',pady=(8,0))
        controls=[title_entry]
        for label,var,width in [('Year',year,7),('Season',season,5),('Episode',episode,5)]:
            ttk.Label(fields,text=label).pack(side='left',padx=(0,5))
            entry=ttk.Entry(fields,textvariable=var,width=width); entry.pack(side='left',padx=(0,14)); controls.append(entry)
        ttk.Label(fields,text='Type').pack(side='left',padx=(0,5))
        type_box=ttk.Combobox(fields,textvariable=kind,values=('Movie','TV'),state='readonly',width=8); type_box.pack(side='left'); controls.append(type_box)
        ttk.Label(body,text='Edit the title and press Enter to search. Select the right title/year, then continue.',style='Muted.TLabel').grid(row=3,column=0,sticky='ew',pady=10)
        table=ttk.Frame(body); table.grid(row=4,column=0,sticky='nsew'); table.columnconfigure(0,weight=1); table.rowconfigure(0,weight=1)
        matches=ttk.Treeview(table,columns=('title','year','provider'),show='headings',selectmode='browse')
        for col,label,width in [('title','Title',440),('year','Year',90),('provider','Database',160)]:
            matches.heading(col,text=label); matches.column(col,width=width,minwidth=70)
        matches.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(table,orient='vertical',command=matches.yview); scroll.grid(row=0,column=1,sticky='ns'); matches.configure(yscrollcommand=scroll.set)
        ttk.Label(body,textvariable=notice,wraplength=810).grid(row=5,column=0,sticky='ew',pady=10)
        bar=ttk.Frame(body); bar.grid(row=6,column=0,columnspan=2,sticky='ew')
        previous=ttk.Button(bar,text='Previous'); previous.pack(side='left')
        database=ttk.Button(bar,text='Database settings...'); database.pack(side='left',padx=8)
        close=ttk.Button(bar,text='Close',command=win.destroy); close.pack(side='right')
        use=ttk.Button(bar,text='Use match & next',style='Primary.TButton'); use.pack(side='right',padx=8)
        skip=ttk.Button(bar,text='Skip for now'); skip.pack(side='right')
        state={'index':0,'busy':False,'results':[],'drafts':{}}
        def save_draft():
            if state['index']<len(items): state['drafts'][state['index']]=(query.get(),year.get(),kind.get(),season.get(),episode.get(),list(state['results']))
        def fill():
            matches.delete(*matches.get_children())
            for i,c in enumerate(state['results']): matches.insert('','end',iid=str(i),values=(c['title'],c.get('year',''),c.get('provider','')))
            if state['results']:
                chosen=items[state['index']].chosen if state['index']<len(items) else None
                selected=next((i for i,c in enumerate(state['results']) if chosen and (c.get('provider'),c.get('id'),c['title'],c.get('year'))==(chosen.get('provider'),chosen.get('id'),chosen['title'],chosen.get('year'))),0)
                matches.selection_set(str(selected))
        def enabled():
            completed=state['index']>=len(items); unsupported=not completed and items[state['index']].status.startswith('Unsupported')
            for control in controls: control.state(['disabled'] if state['busy'] or completed else ['!disabled'])
            if not state['busy'] and not completed:
                type_box.state(['readonly'])
                if kind.get()=='Movie':
                    controls[2].state(['disabled']); controls[3].state(['disabled'])
            for button in (previous,database,use,skip,search_button): button.state(['disabled'] if state['busy'] else ['!disabled'])
            if state['index']==0: previous.state(['disabled'])
            if completed or unsupported:
                search_button.state(['disabled']); use.state(['disabled'])
            if completed: skip.state(['disabled'])
            close.configure(text='Finish' if completed else 'Close')
        def render():
            count=sum(bool(m.chosen) for m in items)
            if state['index']>=len(items):
                viewer.load(None); progress.set('Review complete'); filename.set(f'{count} of {len(items)} files resolved.')
                notice.set(f'{len(items)-count} files remain unresolved. Skipped files can be reviewed again later. Use Organize when ready.')
                state['results']=[]; fill(); enabled(); self.refresh(); return
            m=items[state['index']]; progress.set(f'File {state["index"]+1} of {len(items)} | {count} resolved')
            filename.set(str(m.source)); viewer.load(self.current_path(m))
            draft=state['drafts'].get(state['index'],(m.query,m.year,m.kind,str(m.season if m.season is not None else 1),str(m.episode if m.episode is not None else 1),list(m.candidates)))
            for variable,value in zip((query,year,kind,season,episode),draft[:5]): variable.set(value)
            state['results']=draft[5]; fill()
            notice.set('Unsupported episode pattern. Correct the filename and rescan, or skip this file.' if m.status.startswith('Unsupported') else 'Choose a result by title and release year. Corrections are saved immediately.')
            enabled(); title_entry.focus_set()
        def move(delta):
            if state['busy']: return
            save_draft(); state['index']=max(0,min(len(items),state['index']+delta)); render()
        def search(event=None):
            if state['busy'] or state['index']>=len(items) or self.busy: return 'break'
            if not query.get().strip(): notice.set('Enter a title to search.'); return 'break'
            if year.get() and (len(year.get())!=4 or not year.get().isdigit()): notice.set('Enter a four-digit year or leave it blank.'); return 'break'
            m=items[state['index']]
            if m.status.startswith('Unsupported'): return 'break'
            request=Media(m.source,query.get().strip(),year.get().strip(),0 if kind.get()=='TV' else None,1 if kind.get()=='TV' else None)
            state['busy']=True; enabled(); notice.set('Searching '+History.provider(request)+'...')
            def done(results,error):
                if not win.winfo_exists(): return
                state['busy']=False; state['results']=results; fill(); enabled()
                notice.set(error or (f'{len(results)} results. Select the correct title and year.' if results else 'No results. Try a shorter title, another language, or correct the media type.'))
            def task():
                try:
                    with self.catalog.fresh(): results=self.catalog.search(request)
                    self.events.put(('callback',lambda:done(results,None)))
                except Exception as exc:
                    message=str(exc); self.events.put(('callback',lambda:done([],message)))
            self.run(task); return 'break'
        def choose(event=None):
            if state['busy'] or state['index']>=len(items): return 'break'
            selected=matches.selection()
            if not selected: notice.set('Select a database result first.'); return 'break'
            try:
                resolve_manually(items[state['index']],state['results'][int(selected[0])],query.get(),year.get(),int(season.get()) if kind.get()=='TV' else None,int(episode.get()) if kind.get()=='TV' else None,kind.get())
            except (OSError,ValueError) as exc: notice.set(str(exc)); return 'break'
            save_draft(); self.refresh(); state['index']+=1; render(); return 'break'
        def settings():
            if state['busy']: return
            self.database()
            if win.winfo_exists(): win.grab_set()
        matches.bind('<<TreeviewSelect>>',detail_selected)
        previous.configure(command=lambda:move(-1)); skip.configure(command=lambda:move(1)); use.configure(command=choose)
        search_button.configure(command=search); database.configure(command=settings)
        def changed_type(event=None):
            state['results']=[]; fill(); enabled(); notice.set('Media type changed. Search again for the correct database entries.')
        type_box.bind('<<ComboboxSelected>>',changed_type)
        title_entry.bind('<Return>',search); matches.bind('<Return>',choose); matches.bind('<Double-1>',choose)
        win.bind('<Escape>',lambda event:win.destroy()); render()
    def show_review(self,m):
        win=tk.Toplevel(self); win.title('Choose the correct title'); win.geometry('650x430'); win.transient(self)
        ttk.Label(win,text=m.source.name,wraplength=610).pack(padx=16,pady=12)
        query=tk.StringVar(value=m.query); ttk.Entry(win,textvariable=query).pack(fill='x',padx=16)
        listing=tk.Listbox(win,font=('Segoe UI',11)); listing.pack(fill='both',expand=True,padx=16,pady=12)
        candidates=list(m.candidates)
        def fill():
            listing.delete(0,'end')
            for c in candidates: listing.insert('end',f"{c['title']} ({c['year']}) - {c['provider']}")
        fill()
        def search():
            m.query=query.get().strip()
            def task():
                try:
                    with self.catalog.fresh(): result=self.catalog.search(m)
                    self.events.put(('review',(m,result)))
                except DatabaseSetupRequired as exc:
                    self.events.put(('status',str(exc)))
                    self.events.put(('database_needed',None))
            win.destroy(); self.run(task)
        def choose():
            if not listing.curselection(): return
            m.chosen=candidates[listing.curselection()[0]]; m.status='Ready'; m.cached=False
            History().save(m)
            self.refresh(); win.destroy()
        ttk.Button(win,text='Search again',command=search).pack(side='left',padx=16,pady=12)
        ttk.Button(win,text='Use selected match',command=choose).pack(side='right',padx=16,pady=12)
    def copy(self):
        visible=sorted_media_indices(self.items,VIEW_SORT_FIELDS[self.sort_var.get()],self.descending.get(),self.filter_var.get())
        ready=[self.items[i] for i in visible if self.items[i].status=='Ready' and self.items[i].chosen]
        if not ready: return
        library=self.output_folder()
        mode='move' if self.in_place.get() else 'copy'
        if not library: messagebox.showerror('Folder needed','Choose an output folder.'); return
        verb='Move' if mode=='move' else 'Copy'
        note='Files will be relocated within your media folder. Undo can restore their original paths.' if mode=='move' else 'Originals will be preserved.'
        if self.auto_cleanup.get(): note+='\nAfter success: archive common source junk and remove empty source folders.'
        if not messagebox.askyesno('Organize library',f'{verb} {len(ready)} media files and matching subtitles into:\n{library}\n\n{note}'): return
        options=self.options; cleanup=self.auto_cleanup.get(); source=self.source.get()
        self.save_settings()
        def task():
            self.previews.close(wait=True)
            result,self.journal=sort_and_finish(ready,library,source,mode,options,cleanup,lambda status:self.events.put(('refresh',None)))
            cleaned=result['cleanup']
            self.events.put(('status',f"{verb} complete: {result['sorted']} of {len(ready)} organized; {cleaned['files']} source junk files archived, {cleaned['folders']} empty folders removed. {len(cleaned['skipped'])+len(result['warnings'])} cleanup issues."))
            if result['warnings']: self.events.put(('error','\n'.join(result['warnings'])))
            if cleaned['skipped']: self.events.put(('cleanup_report',cleaned))
        self.run(task)
    def undo(self):
        journals=sorted(DATA.glob('run-*.jsonl')) if DATA.exists() else []
        journal=self.journal or (journals[-1] if journals else None)
        if not journal: return
        if not messagebox.askyesno('Undo last operation','Undo the latest operation? Moved, renamed and cleaned-up files return to their original paths; copies are removed and empty folders are restored. Modified files and occupied original paths are skipped.'): return
        def task():
            self.previews.close(wait=True)
            self.events.put(('status',f'Undone: {undo(journal)} file and folder operations reversed.'))
        self.run(task)
    def close(self):
        if self.busy: messagebox.showinfo('Work in progress','Please wait for the current operation to finish before closing.'); return
        self.hover_preview.hide(); self.previews.close(wait=True)
        self.destroy()
if __name__=='__main__': App().mainloop()
