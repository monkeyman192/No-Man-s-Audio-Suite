#NMSSE (No Man's Sky Sound Editor)

__author__ = "monkeyman192"
__version__ = "0.5"

from tkinter import *
from tkinter import filedialog, simpledialog
from tkinter import font
from tkinter import ttk
from tkinter import messagebox

# misc functions for processing data etc
import pickle
from os import path, chdir, remove, walk, listdir, makedirs
import subprocess
import shutil
import threading

# play audio
import pyglet

from collections import OrderedDict

root = Tk()

import xml.etree.ElementTree as ET

from BNKcompiler import *
from xml_worker import xml_worker
from txt_worker import txt_worker

DEFAULTSETTINGS = {'audioPath': "",
                   'additionPath': "TO_ADD",
                   'outputPath': "OUTPUT",
                   'workingPath': "TEMP",
                   'toolPath': 'Tools',
                   'convertedPath': 'CONVERTED'}
APPSPATH = 'Apps'

def fnvhash(s):
    s = s.lower()
    hval = 0x811c9dc5 # Magic value for 32-bit fnv1 hash initialisation.
    fnvprime = 0x01000193
    fnvsize = 2**32
    if not isinstance(s, bytes):
        s = s.encode("UTF-8", "ignore")
    for byte in s:
        hval = (hval * fnvprime) % fnvsize
        hval = hval ^ byte
    return hval

# not sure if I will use the following 4 classes. Maybe later to make things a bit more powerful... *maybe*

class NMSAudio():
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', None)

class StreamedFile(NMSAudio):
    def __init__(self, **kwargs):
        super(StreamedFile, self).__init__(**kwargs)

        self.canPlay = kwargs.get('canPlay', False)     # if True the file exists in the CONVERTED folder
        self.filepath = kwargs.get('filePath', None)    

class Event(NMSAudio):
    def __init__(self, **kwargs):
        super(Event, self).__init__(**kwargs)

class IncludedFile(NMSAudio):
    def __init__(self, **kwargs):
        super(IncludedFile, self).__init__(**kwargs)
        self.canPlay = kwargs.get('canPlay', False)     # if True the file exists in the CONVERTED folder
        self.beenExtracted = kwargs.get('beenExtracted', False)     # if true the file exists in the TEMP folder
        self.filepath = kwargs.get('filePath', None)

class GUI(Frame):
    def __init__(self, master):
        self.master = master
        Frame.__init__(self, self.master)

        self.textFont = font.Font(self, "Calibiri", "12")

        self.SoundBanksData = []     # this will hold all the soundbank Element objects that can be read from directly

        self.selectedAudioListType = 'Str'      # other possibilities: 'Inc' and 'Act'
        self.searchTerm = StringVar()

        self.projectName = StringVar()      # name of the project

        # progress bar stuff:
        self.num_files = 100
        self.curr_progress = IntVar()
        self.threadLock = threading.Lock()

        # create all the widgets
        self.createWidgets()
        self.createMenus()

        # audio playback variables:
        self.song = None        # the currently playing song (if any)
        self.player = None      # the pyglet player object (so we can pause on exit if required)
        self.isPlaying = False  # whether or not we are currently playing something

        try:
            with open('settings.pkl', 'rb') as f:
                self.settings = pickle.load(f)
            # add a check to see if the DEFAULTSETTINGS data is larger than before, if so, merge any new default settings into settings
            if len(self.settings) != DEFAULTSETTINGS:
                for setting in DEFAULTSETTINGS:
                    if self.settings.get(setting, None) is None:
                        self.settings[setting] = DEFAULTSETTINGS[setting]
        except:
            self.settings = DEFAULTSETTINGS
        self.settings['workingPath'] = path.abspath(self.settings['workingPath'])
        self.settings['workingPath'] = path.abspath('TEMP')
        self.settings['convertedPath'] = path.abspath('CONVERTED')
        self.settings['toolPath'] = path.abspath('Tools')
        print(self.settings)

        if not path.exists(self.settings['audioPath']):
            messagebox.showwarning("Bad Paths!", message = "Paths in settings are incorrect. Please reset!")
            self.getPaths()

        self.generateSoundBankData()

        # populate the list of soundbanks
        self.populateSoundBankList()

    def createWidgets(self):
        # entry for project name
        nameFrame = Frame(self.master)
        nameLabel = Label(nameFrame, text = "Project Name: ")
        nameLabel.pack(side = LEFT)
        nameEntry = Entry(nameFrame, textvariable = self.projectName)
        nameEntry.pack(side = LEFT)
        nameFrame.pack()
        
        # top panel for ListFrames
        self.ListFrame = Frame(self.master)
        
        # left panel for the sound banks list
        self.SoundBanksFrame = Frame(self.ListFrame)
        SBListFrame = Frame(self.SoundBanksFrame)
        self.SoundBanksListView = ttk.Treeview(SBListFrame, columns = ['Sound Bank Name'], displaycolumns = '#all', selectmode = 'extended')
        self.SoundBanksListView.heading("Sound Bank Name", text = "Sound Bank Name", command = lambda _col = "Sound Bank Name": self.treeview_sort_column(self.SoundBanksListView, _col, False))
        self.SoundBanksListView.column("Sound Bank Name", stretch = True, width = 300)
        self.SoundBanksListView["show"] = 'headings'
        sb_ysb = ttk.Scrollbar(SBListFrame, orient=VERTICAL, command=self.SoundBanksListView.yview)
        sb_ysb.pack(side=RIGHT, fill=Y)
        self.SoundBanksListView.configure(yscroll=sb_ysb.set)
        self.SoundBanksListView.pack(fill=BOTH, expand=1)
        self.SoundBanksListView.bind("<<TreeviewSelect>>", self.soundbankSelectionChange)       # <<TreeviewSelect>>, <ButtonRelease-1>
        SBListFrame.pack(fill=BOTH, expand=1)
        self.SoundBanksFrame.pack(fill=BOTH, expand=1, side = LEFT)

        # right panel for audio list
        self.AudioFrame = Frame(self.ListFrame)
        # First, we will have a small panel that is static, and have 3 buttons,
        # allowing you to pick what type of audio list you want to show (streamed, included or actions)
        self.SelectorFrame = Frame(self.AudioFrame)
        self.StreamedButton = Button(self.SelectorFrame, text = "Streamed", command = self.show_streamed, state = DISABLED)
        self.StreamedButton.pack(side = LEFT)
        self.IncludedButton = Button(self.SelectorFrame, text = "Included", command = self.show_included)
        self.IncludedButton.pack(side = LEFT)
        self.ActionsButton = Button(self.SelectorFrame, text = "Actions", command = self.show_actions)
        self.ActionsButton.pack(side = LEFT)
        self.SelectorFrame.pack()

        # we will have a separate frame and treeview for each set of data, so that we aren't having to reset the data each time (selected values carry over hopefully)

        # the frame for actions
        self.ActionFrame = Frame(self.AudioFrame)
        ActionListFrame = Frame(self.ActionFrame)
        self.ActionListView = ttk.Treeview(ActionListFrame, columns = ['Action Name'], displaycolumns = '#all', selectmode = 'extended')
        self.ActionListView.heading("Action Name", text = "Action Name", command = lambda _col = "Action Name": self.treeview_sort_column(self.ActionListView, _col, False))
        self.ActionListView.column("Action Name", stretch = True, width = 400)
        self.ActionListView["show"] = 'headings'
        self.ActionListView.tag_configure('modified', background='green')
        a_ysb = ttk.Scrollbar(ActionListFrame, orient=VERTICAL, command=self.ActionListView.yview)
        a_ysb.pack(side=RIGHT, fill=Y)
        self.ActionListView.configure(yscroll=a_ysb.set)
        self.ActionListView.pack(fill=BOTH, expand=YES)
        ActionListFrame.pack(fill=BOTH, expand=YES)
        if self.selectedAudioListType == 'Act':
            self.ActionFrame.pack(fill=BOTH, expand=YES)

        # the frame for included audios
        self.IncludedFrame = Frame(self.AudioFrame)
        IncludedListFrame = Frame(self.IncludedFrame)
        self.IncludedListView = ttk.Treeview(IncludedListFrame, columns = ['Included File', 'Id'], displaycolumns = '#all', selectmode = 'extended')
        self.IncludedListView.heading("Included File", text = "Included File", command = lambda _col = "Included File": self.treeview_sort_column(self.IncludedListView, _col, False))
        self.IncludedListView.heading("Id", text = "Id", command = lambda _col = "Id": self.treeview_sort_column(self.IncludedListView, _col, False))
        self.IncludedListView.column("Included File", stretch = True, width = 350)
        self.IncludedListView.column("Id", stretch = True, width = 50)
        self.IncludedListView["show"] = 'headings'
        self.IncludedListView.tag_configure('modified', background='green')
        self.IncludedListView.bind('<ButtonRelease-1>', lambda *args: self.check_file_exists(self.IncludedListView))
        i_ysb = ttk.Scrollbar(IncludedListFrame, orient=VERTICAL, command=self.IncludedListView.yview)
        i_ysb.pack(side=RIGHT, fill=Y)
        self.IncludedListView.configure(yscroll=i_ysb.set)
        self.IncludedListView.pack(fill=BOTH, expand=YES)
        IncludedListFrame.pack(fill=BOTH, expand=YES)
        if self.selectedAudioListType == 'Inc':
            self.IncludedFrame.pack(fill=BOTH, expand=YES)

        # the frame for streamed audios
        self.StreamedFrame = Frame(self.AudioFrame)
        StreamedListFrame = Frame(self.StreamedFrame)
        self.StreamedListView = ttk.Treeview(StreamedListFrame, columns = ['Streamed File', 'Id'], displaycolumns = '#all', selectmode = 'extended')
        self.StreamedListView.heading("Streamed File", text = "Streamed File", command = lambda _col = "Streamed File": self.treeview_sort_column(self.StreamedListView, _col, False))
        self.StreamedListView.heading("Id", text = "Id", command = lambda _col = "Id": self.treeview_sort_column(self.StreamedListView, _col, False))
        self.StreamedListView.column("Streamed File", stretch = True, width = 350)
        self.StreamedListView.column("Id", stretch = True, width = 50)
        self.StreamedListView["show"] = 'headings'
        self.StreamedListView.tag_configure('modified', background='green')
        self.StreamedListView.bind('<ButtonRelease-1>', lambda *args: self.check_file_exists(self.StreamedListView))
        s_ysb = ttk.Scrollbar(StreamedListFrame, orient=VERTICAL, command=self.StreamedListView.yview)
        s_ysb.pack(side=RIGHT, fill=Y)
        self.StreamedListView.configure(yscroll=s_ysb.set)
        self.StreamedListView.pack(fill=BOTH, expand=YES)
        StreamedListFrame.pack(fill=BOTH, expand=YES)
        if self.selectedAudioListType == 'Str':
            self.StreamedFrame.pack(fill=BOTH, expand=YES)

        # this frame contains the search functionality
        self.searchFrame = Frame(self.AudioFrame)
        sortLabel = Label(self.searchFrame, text = "Search: ")
        sortLabel.pack(side = LEFT)
        seachCommand = self.register(self.SearchAudioList)
        self.SoundsSortEntry = Entry(self.searchFrame, textvariable = self.searchTerm, validatecommand = (seachCommand, '%P'), validate = 'key')
        self.SoundsSortEntry.pack(side = LEFT)
        self.progbar = ttk.Progressbar(self.searchFrame, maximum=self.num_files, variable=self.curr_progress)
        self.progbar.pack(side = LEFT)
        self.searchFrame.pack()

        # frame for playback/conversion of audio files
        self.playbackFrame = Frame(self.AudioFrame)
        self.convertButton = Button(self.playbackFrame, text = "Convert", command = self.convert_audio)
        self.convertButton.pack(side = LEFT)
        self.playButton = Button(self.playbackFrame, text = "Play", command = self.play_audio, state = DISABLED)
        self.playButton.pack(side = LEFT)
        self.stopButton = Button(self.playbackFrame, text = "Stop", command = self.stop_audio, state = DISABLED)
        self.stopButton.pack(side = LEFT)
        self.playbackBar = ttk.Progressbar(self.playbackFrame, mode = 'determinate')
        self.playbackBar.pack(side = LEFT)
        self.playbackFrame.pack()
        

        self.AudioFrame.pack(fill=BOTH, expand=YES, side = LEFT)

        # panel for buttons to run various functions
        self.AudioButtonFrame = Frame(self.ListFrame)
        self.unpack_button = Button(self.AudioButtonFrame, text = "Unpack All", command = self.unpack_soundbank_threaded)
        self.unpack_button.pack()
        self.unpack_select_button = Button(self.AudioButtonFrame, text = "Unpack Selected", command = self.unpack_soundbank_threaded_selected)
        self.unpack_select_button.pack()
        self.repack_button = Button(self.AudioButtonFrame, text = "Repack", command = self.repack_soundbank_threaded)
        self.repack_button.pack()
        self.add_button = Button(self.AudioButtonFrame, text = "Add", command = self.add_audio_precheck, state = DISABLED)
        self.add_button.pack()
        self.replace_button = Button(self.AudioButtonFrame, text = "Replace", command = self.replace_audio)#, state = DISABLED)
        self.replace_button.pack()
        self.AudioButtonFrame.pack(side=LEFT)

        self.ListFrame.pack(fill=BOTH, expand=YES)

        self.BottomButtonFrame = Frame(self.master)
        quit_button = Button(self.BottomButtonFrame, text = "Exit", command=self.quit)
        quit_button.pack(side = RIGHT)
        self.BottomButtonFrame.pack()

    def createMenus(self):
        # create the menu that has a number of options in it
        self.menuBar = Menu(self.master)
        # first we will have a menu drop down for options
        self.setupMenu = Menu(self.menuBar, tearoff=0)
        self.menuBar.add_cascade(label="Setup", menu=self.setupMenu)

        """ All the stuff going in the setup menu drop down """
        self.setupMenu.add_command(label="Set AUDIO directory", command = self.getAudioPath)
        self.setupMenu.add_command(label="Set output directory", command = self.getOutputPath)
        self.setupMenu.add_command(label="Set working directory", command = self.getAdditionPath)

        self.master.config(menu = self.menuBar)

    def checkButtonStates(self):
        # this will check whether or not the selected soundbank has been unpacked or not.
        # If so, activate the buttons to allow the user to add/remove/replace audios
        iid = self.SoundBanksListView.focus()
        sb_name = self.SoundBanksListView.item(iid)['values'][0]
        if path.exists(path.join(self.settings['workingPath'], sb_name.upper())):
            self.add_button.config(state = NORMAL)
            self.replace_button.config(state = NORMAL)
        else:
            self.add_button.config(state = NORMAL)
            if self.selectedAudioListType == 'Inc':
                self.replace_button.config(state = DISABLED)
            else:
                self.replace_button.config(state = NORMAL)
        # always have the replace button disabled for actions
        if self.selectedAudioListType == 'Act':
            self.replace_button.config(state = DISABLED)
        if self.selectedAudioListType != 'Inc':
            self.unpack_select_button.config(state = DISABLED)
        if self.selectedAudioListType == 'Inc':
            self.unpack_select_button.config(state = NORMAL)            

    def show_streamed(self):
        # remove the current treeview and replace it with the list of streamed audios
        self.StreamedButton.config(state = DISABLED)
        if self.selectedAudioListType == 'Act':
            self.ActionsButton.config(state = NORMAL)
            self.ActionFrame.pack_forget()
        elif self.selectedAudioListType == 'Inc':
            self.IncludedButton.config(state = NORMAL)
            self.IncludedFrame.pack_forget()
        self.searchFrame.pack_forget()
        self.playbackFrame.pack_forget()
        self.selectedAudioListType = 'Str'
        self.StreamedFrame.pack(fill=BOTH, expand=YES)
        self.searchFrame.pack()
        self.playbackFrame.pack()
        self.checkButtonStates()
        if self.searchTerm.get() != '':
            self.SearchAudioList(self.searchTerm.get())

    def show_actions(self):
        # remove the current treeview and replace it with the list of actions
        self.ActionsButton.config(state = DISABLED)
        if self.selectedAudioListType == 'Str':
            self.StreamedButton.config(state = NORMAL)
            self.StreamedFrame.pack_forget()
        elif self.selectedAudioListType == 'Inc':
            self.IncludedButton.config(state = NORMAL)
            self.IncludedFrame.pack_forget()
        self.searchFrame.pack_forget()
        self.playbackFrame.pack_forget()
        self.selectedAudioListType = 'Act'
        self.ActionFrame.pack(fill=BOTH, expand=YES)
        self.searchFrame.pack()
        self.playbackFrame.pack()
        self.checkButtonStates()
        if self.searchTerm.get() != '':
            self.SearchAudioList(self.searchTerm.get())

    def show_included(self):
        # remove the current treeview and replace it with the list of included audios
        self.IncludedButton.config(state = DISABLED)
        if self.selectedAudioListType == 'Str':
            self.StreamedButton.config(state = NORMAL)
            self.StreamedFrame.pack_forget()
        if self.selectedAudioListType == 'Act':
            self.ActionsButton.config(state = NORMAL)
            self.ActionFrame.pack_forget()
        self.searchFrame.pack_forget()
        self.playbackFrame.pack_forget()
        self.selectedAudioListType = 'Inc'
        self.IncludedFrame.pack(fill=BOTH, expand=YES)
        self.searchFrame.pack()
        self.playbackFrame.pack()
        self.checkButtonStates()
        if self.searchTerm.get() != '':
            self.SearchAudioList(self.searchTerm.get())

    def generateSoundBankData(self):
        tree = ET.ElementTree()
        tree.parse(path.join(self.settings['audioPath'], 'SOUNDBANKSINFO.XML'))
        self.SoundBanksData = list(tree.find('SoundBanks').iter("SoundBank"))
        
    def searchSoundBanks(self, name):
        # search the list of soundbank nodes for the correct one and return it
        # receive the name as we can hash it to get the Id which can then be found
        language_sb = False
        if name.startswith('Vocal_Localised'):
            language = name[len('Vocal_Localised') + 2 : -1]
            name = 'Vocal_Localised'
            language_sb = True
        Id = str(fnvhash(name))
        for sb in self.SoundBanksData:
            if language_sb == False:
                if sb.attrib['Id'] == Id:
                    return sb
            else:
                if sb.attrib['Id'] == Id and sb.attrib['Language'] == language:
                    return sb

    def SearchAudioList(self, term):
        # populate each of the trees with only the entries that contain the substring 'term'
        if self.selectedAudioListType == 'Str':
            self.populateStreamedList(compare = term)
        if self.selectedAudioListType == 'Act':
            self.populateActionList(compare = term)
        if self.selectedAudioListType == 'Inc':
            self.populateIncludedList(compare = term)
        return True

    @staticmethod
    def getEvents(soundbank):
        IncludedEvents = soundbank.find('IncludedEvents')
        try:
            return IncludedEvents.findall('Event')
        except:
            return []

    @staticmethod
    def getStreamed(soundbank):
        ReferencedStreamedFiles = soundbank.find('ReferencedStreamedFiles')
        try:
            return ReferencedStreamedFiles.findall('File')
        except:
            return []

    @staticmethod
    def getIncluded(soundbank):
        IncludedMemoryFiles = soundbank.find('IncludedMemoryFiles')
        try:
            return IncludedMemoryFiles.findall('File')
        except:
            return []
    
    def treeview_sort_column(self, tv, col, reverse):
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        l.sort(reverse=reverse)

        # rearrange items in sorted positions
        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)

        # reverse sort next time
        tv.heading(col, command=lambda: self.treeview_sort_column(tv, col, not reverse))

    def soundbankSelectionChange(self, event):
        # container for functions to be run when the selection in the soundbank list changes
        self.checkButtonStates()
        self.populateActionList()
        self.populateIncludedList()
        self.populateStreamedList()
        if self.searchTerm.get() != '':
            self.SearchAudioList(self.searchTerm.get())

    def populateSoundBankList(self):
        # this will populate the soud bank list with all the names
        for sb in self.SoundBanksData:
            name = sb.find('ShortName').text
            if name == 'Vocal_Localised':
                region = sb.find('Path').text.split('\\')[0]
                name = '{0}_[{1}]'.format(name, region)
            elif name == 'NMS_Audio_Persistent':
                self.SoundBanksListView.insert("", 0, values=name)
            elif name not in ["Init", "ConvVerb_Impulses"]:
                self.SoundBanksListView.insert("", "end", values=name)
            
    def populateActionList(self, compare = ''):
        # this will find what sound bank is selected and populate the action list with the list of actions in the bank

        # first clear the list
        self.ActionListView.delete(*self.ActionListView.get_children())

        # now get the info and populate
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        for event in self.getEvents(soundbank):
            if compare == '':
                self.ActionListView.insert("", "end", values=event.attrib["Name"])
            else:
                if compare.upper() in event.attrib["Name"].upper():
                    self.ActionListView.insert("", "end", values=event.attrib["Name"])

    def populateStreamedList(self, compare = ''):
        # this will find what sound bank is selected and populate the action list with the list of actions in the bank
        # compare is the seacrh string

        # first clear the list
        self.StreamedListView.delete(*self.StreamedListView.get_children())

        # now get the info and populate
        sb_name = self.getSelectedSoundbankName()

        # we need to do one extra step because the names of streamed files are not in the soundbanksinfo.xml, but only in the actual <soundbank_name>.xml
        sb_tree = ET.ElementTree()
        sb_tree.parse(path.join(self.settings['audioPath'], '{}.XML'.format(sb_name.upper())))
        soundbank = sb_tree.find('SoundBanks').find("SoundBank")
        
        #soundbank = self.searchSoundBanks(sb_name)
        for event in self.getStreamed(soundbank):
            if compare == '':
                # just display the full list with no culling
                self.StreamedListView.insert("", "end", values=[event.find("ShortName").text, event.attrib['Id']])
            else:
                # display only the entries in the list that contain the substring
                if compare.upper() in event.find("ShortName").text.upper() or compare.upper() in event.attrib["Id"].upper():
                    self.StreamedListView.insert("", "end", values=[event.find("ShortName").text, event.attrib['Id']])

    def populateIncludedList(self, compare = ''):
        # this will find what sound bank is selected and populate the action list with the list of actions in the bank

        # first clear the list
        self.IncludedListView.delete(*self.IncludedListView.get_children())

        # now get the info and populate
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        for event in self.getIncluded(soundbank):
            if compare == '':
                self.IncludedListView.insert("", "end", values=[event.find("ShortName").text, event.attrib['Id']])
            else:
                if compare.upper() in event.find("ShortName").text.upper() or compare.upper() in event.attrib["Id"].upper():
                    self.IncludedListView.insert("", "end", values=[event.find("ShortName").text, event.attrib['Id']])

    def unpack_soundbank_threaded_selected(self, selectionMode = 'many'):
        if selectionMode == 'many':
            selected_ids = self.getSelectedAudioIds(self.IncludedListView)
        elif selectionMode == 'single':
            selected_ids = [self.IncludedListView.item(self.IncludedListView.focus())['values'][1]]     # initialise in list for compatibility
            
        #self.num_files = num_files
        self.progbar['maximum'] = len(selected_ids)
        unpack_thread = threading.Thread(target = lambda: self.unpack_soundbank(selected_ids))
        unpack_thread.start()

    def unpack_soundbank_threaded(self, speedmode = False):
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        lst = self.getIncluded(soundbank)
        if lst is not None:
            num_files = len(lst)
        else:
            num_files = 0
        #self.num_files = num_files
        self.progbar['maximum'] = num_files
        unpack_thread = threading.Thread(target = lambda: self.unpack_soundbank(speedmode = speedmode))
        unpack_thread.start()

    def unpack_soundbank(self, specific_ids = [], speedmode = False):
        self.threadLock.acquire()
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        # get the actual path of the soundbank itself, and then move it into the APPSPATH
        soundbank_path = path.join(self.settings['audioPath'], soundbank.find('Path').text.upper())
        b = BNK(sb_name.upper(), soundbank_path, path.join(self.settings['workingPath'], sb_name.upper()), counter = self.curr_progress)
        b.extract(specific_ids, speedmode = speedmode)
        self.checkButtonStates()
        self.threadLock.release()

    def repack_soundbank_threaded(self, overrides = None):
        # override is a path to override specifically running this on the currently selected soundbank
        repack_thread = threading.Thread(target = lambda: self.repack_soundbank(overrides))
        repack_thread.start()

    def repack_soundbank(self, overrides = None):
        # override is a path to override specifically running this on the currently selected soundbank
        self.threadLock.acquire()
        # we need to do a few things here
        # first, get selected soundbank:
        if overrides is None:
            sb_name = self.getSelectedSoundbankName()
            soundbank = self.searchSoundBanks(sb_name)
            lst = self.getIncluded(soundbank)
            if lst is not None:
                num_files = len(lst)
            else:
                num_files = 0
            #self.num_files = num_files
            self.progbar['maximum'] = num_files
            output_path = path.join(self.settings['outputPath'], '{}.BNK'.format(sb_name.upper()))
            b = BNK(sb_name.upper(), path.join(self.settings['workingPath'], sb_name.upper()), output_path, counter = self.curr_progress)
            b.recompile()
        else:
            # this is a dictionary with keys input and output:
            output_path = overrides.get('output')
            input_path = overrides.get('input')
            name = overrides.get('name')
            b = BNK(name, input_path, output_path)
            b.recompile()
        self.threadLock.release()


    @staticmethod
    def getNumFiles(source, dtype):
        # returns the number of files in a directory (source) of type (dtype)
        counter = 0
        for root, dirs, files in walk(source):
            for file in files:
                #name = path.splitext(file)[0]
                if path.splitext(file)[1] == dtype:
                    counter += 1
        return counter

    def add_audio_precheck(self):
        if self.projectName.get() != '':
            self.add_audio()
        else:
            print("enter a project name!!")
    
    def add_audio(self):
        
        # get the name of the currently selected bank
        selected_sb_name = self.getSelectedSoundbankName()
        #soundbank = self.searchSoundBanks(sb_name)
        
        add_path = self.settings['additionPath']
        working_path = path.join(self.settings['workingPath'], selected_sb_name.upper())
        out_path = path.join(self.settings['outputPath'], self.projectName.get())
        if not path.exists(out_path):
            makedirs(out_path)

        # get the soundbankinfo containing the data about the files to be added
        soundbankinfo_add = filedialog.askopenfilename(title = "Select the Soundbanksinfo file produced by Wwise",
                                                       initialdir = self.settings['additionPath'],
                                                       filetypes = [('Soundbanksinfo', '*.xml')])
        # update the working path for concise-ness
        add_path = path.dirname(soundbankinfo_add)

        print(add_path)

        """ there are a few things we need to do:
        1. get the list of included file and copy them to the temp folder. This is done by decompiling the bnk. Move .hirc also.
        2. repack the bnk with all the new files. bnk files are being added to needs to be unpacked. Write a check for this?
        3. merge the text and xml data into the original one
        4. move any streamed files to the output folder. Now everything should be in the output folder

        """
        if soundbankinfo_add != '':
            # check to make sure that the bnk, txt and xml files are also in the same directory
            tree = ET.ElementTree()
            tree.parse(soundbankinfo_add)
            SoundBanksData = list(tree.find('SoundBanks').iter("SoundBank"))
            for sb in iter(SoundBanksData):
                if sb.attrib['Id'] == '1355168291':
                    # this is the hash of the init soundbank
                    SoundBanksData.remove(sb)
            # we now have just the soundbank data for the soundbanks that include data to be added, not including Init.
            # Not sure what to do if we have more than one soundbank... We'll see...
            # let's just assume there is only one...
            sb = SoundBanksData[0]
            sb_name = sb.find("ShortName").text
            events = self.getEvents(sb)
            streamed_ids = [a.attrib['Id'] for a in self.getStreamed(sb)]
            included_ids = [a.attrib['Id'] for a in self.getIncluded(sb)]
            print(streamed_ids)
            print(included_ids)
            
            # copy the required files from the AUDIO folder:
            shutil.copy(path.join(self.settings['audioPath'], "{}.TXT".format(selected_sb_name)), out_path)
            shutil.copy(path.join(self.settings['audioPath'], "{}.XML".format(selected_sb_name)), out_path)
            shutil.copy(path.join(self.settings['audioPath'], "SOUNDBANKSINFO.XML"), out_path)
            # merge the txt file
            txt_worker(path.join(add_path, '{}.txt'.format(sb_name)), path.join(out_path, "{}.TXT".format(selected_sb_name)))
            # merge the wwise generated soundbanksinfo.xml file into the soundbanksinfo and original xml files
            xml_worker(path.join(add_path, 'SoundbanksInfo.xml'.format(selected_sb_name)),
                       path.join(out_path, "{}.XML".format(selected_sb_name)), selected_sb_name, sbinfo = False)
            xml_worker(path.join(add_path, 'SoundbanksInfo.xml'), path.join(out_path, "SOUNDBANKSINFO.XML"), selected_sb_name, sbinfo = True)

            # first, let's unpack the sounbank produced by wwise to get any included audios and the hirc data:
            soundbank_path = path.join(add_path, '{}.bnk'.format(sb_name))
            b = BNK(sb_name.upper(), soundbank_path, path.join(self.settings['workingPath'], sb_name.upper()))
            b.extract()

            # any streamed files need to be moved to the output folder first so we can run the bnk recompile to add the new included files if any.
            print("Unpacking original bank")
            self.unpack_soundbank_threaded(speedmode = True)     # needs to be done un-threaded so that the repacking process waits...
            print("Finished unpacking bank")
            
            for root, dirs, files in walk(path.join(self.settings['workingPath'], sb_name.upper())):
                for file in files:
                    if path.splitext(file)[0] in included_ids:
                        # if the names of the file is in the list of included ids, then we move to the working directory
                        shutil.copy(path.join(root, dirs, file), working_path)
                    if path.splitext(file)[1] == 'hirc':
                        # also move any hirc stuff over
                        shutil.copy(path.join(root, dirs, file), working_path)
            # now repack the whole lot
            print("Repacking bank")
            print(working_path)
            self.repack_soundbank_threaded(overrides = {'input':working_path, 'output':path.join(out_path, '{}.BNK'.format(selected_sb_name.upper())), 'name':selected_sb_name})
            print("Finished repacking bank")

            # now move any streamed files to the output path also
            for root, dirs, files in walk(add_path):
                for file in files:
                    print(path.splitext(file)[0])
                    if path.splitext(file)[0] in streamed_ids:

                        shutil.copy(path.join(root, file), out_path)

        """
        for folder in listdir(add_path):
            proj_path = path.join(add_path, folder)
            print(proj_path)

            # first, let's extract the HIRC info from the BNK:
            b = BNK('scarytest', path.join(proj_path, 'scarytest.bnk'), working_path, mode = 'extract')

        # merge the wwise generated and original txt files
        txt_worker(path.join(add_path, 'scarytest', 'scarytest.txt'), path.join(working_path, "{}.TXT".format(sb_name)))

        # merge the wwise generated soundbanksinfo.xml file into the soundbanksinfo and original xml files
        xml_worker(path.join(add_path, 'scarytest', 'SoundbanksInfo.xml'), path.join(working_path, "{}.XML".format(sb_name)), sb_name, ignore_streamed = True)
        xml_worker(path.join(add_path, 'scarytest', 'SoundbanksInfo.xml'), path.join(working_path, "SOUNDBANKSINFO.XML"), sb_name)
        """

    def getSelectedSoundbankName(self):
        iid = self.SoundBanksListView.focus()
        return self.SoundBanksListView.item(iid)['values'][0]

    def check_file_exists(self, tview):
        iid = tview.focus()
        sb_id = tview.item(iid)['values'][1]
        new_file = path.join(self.settings['convertedPath'], "{}.ogg".format(sb_id))
        if path.exists(new_file):
            self.playButton.configure(state = NORMAL)
            self.stopButton.configure(state = NORMAL)
        else:
            self.playButton.configure(state = DISABLED)
            self.stopButton.configure(state = DISABLED)

    @staticmethod
    def getSelectedAudioIds(tview):
        # get the ID of the selected audio event (will only work for streamed or included audios)
        try:
            iid = tview.selection()
            ids = []
            for i in iid:
                ids.append(tview.item(i)['values'][1])
            return ids
        except:
            # raise an index error indicating that the values aren't found (or maybe the treeview has no selection?)
            raise IndexError

    @staticmethod
    def highlightSelectedAudioId(tview):
        # whatever element in the list is selected, highlight it (change background)
        tview.item(tview.focus(),  tag = 'modified')

    def replace_audio(self):
        out_path = self.settings['outputPath']
        working_path = self.settings['workingPath']
        # we'll get the user to specify the file:
        replacement_file = filedialog.askopenfilename(title = "Select the audio to use as replacement",
                                                      initialdir = self.settings['additionPath'],
                                                      filetypes = [('WEM file', '*.wem')])
        if replacement_file != '':
            # make sure something has actually been selected
            if self.selectedAudioListType == 'Str':
                # in this case we don't need to do any repacking of the bnk. We can simply replace the .wem in the AUDIO folder (ie. output folder)
                wem_id = self.getSelectedAudioId(self.StreamedListView)
                shutil.copy(replacement_file, path.join(out_path, '{}.WEM'.format(wem_id)))
                self.highlightSelectedAudioId(self.StreamedListView)
            elif self.selectedAudioListType == 'Inc':
                wem_id = self.getSelectedAudioId(self.IncludedListView)
                # now, we need to extract the entire bnk into the working directory, replace the existing file with the replacement one, then repack.
                wem_id = self.getSelectedAudioId(self.IncludedListView)
                shutil.copy(replacement_file, path.join(working_path, self.getSelectedSoundbankName().upper(), '{}.WEM'.format(wem_id)))
                self.highlightSelectedAudioId(self.IncludedListView)

    def get_selectedSB(self):
        # simply returns the treeview that is currently selected
        if self.selectedAudioListType == 'Str':
            return self.StreamedListView
        elif self.selectedAudioListType == 'Inc':
            return self.IncludedListView
        elif self.selectedAudioListType == 'Act':
            return self.ActionListView

    def convert_audio(self):
        # we need to first figure out what is selected
        sb_ids = self.getSelectedAudioIds(self.get_selectedSB())

        # convert any selected files
        for sb_id in sb_ids:
            new_file = path.join(self.settings['convertedPath'], "{}.ogg".format(sb_id))

            new_path = path.join(self.settings['convertedPath'], "{}.WEM".format(sb_id))
            if self.selectedAudioListType == 'Str':
                # the path of the file will simply be the audio path + filename
                # we need to move this file to converted, then pass *this* path to the converter
                orig_path = path.join(self.settings['audioPath'], "{}.WEM".format(sb_id))
                # copy the file from the AUDIO folder to the converted folder
                shutil.copy(orig_path, new_path)
            else:
                # in this case we also need to extract the individual file from the bnk
                self.unpack_soundbank([sb_id])
                orig_path = path.join(self.settings['workingPath'], self.getSelectedSoundbankName().upper(), "{}.WEM".format(sb_id))
                # copy the file from the TEMP folder to the converted folder
                shutil.copy(orig_path, new_path)
            # then convert it within that folder
            self.conv_wem(new_path)
            # and remove the original wem to make it less cluttered
            remove(new_path)

        # finally, we call the playback button check to cause the play button to be active again
        self.check_file_exists(self.get_selectedSB())

    def play_audio(self):
        # gets the selected audio and plays it (only one at a time)
        sb_ids = self.getSelectedAudioIds(self.get_selectedSB())

        if len(sb_ids) != 1:
            # exit function and raise an error in the program stating only one file can be played at a time
            messagebox.showwarning("Invalid selection!", message = "You can only playback one file at a time.")
            return
        else:
            new_file = path.join(self.settings['convertedPath'], "{}.ogg".format(sb_ids[0]))
            if path.exists(new_file):
                # define a simple function here to do playback                
                print('play the audio')
                self.song = pyglet.media.load(new_file)
                self.player = self.song.play()

                self.update_player_progress(firsttime = True)

                # we also want to use the progress bar as a rudimentary playback tracker
            else:
                print("file doesn't exist?!?!")

    def stop_audio(self):
        self.player.pause()
        self.isPlaying = False

    def update_player_progress(self, firsttime = False):
        progress = min(100*self.player.time/self.song.duration, 100)
        if firsttime:
            self.isPlaying = True
            progress += 0.001
        print(progress)
        print(self.isPlaying)
        self.playbackBar["value"] = progress
        if progress == 0.0:
            self.isPlaying = False
        if self.isPlaying:
            self.after(100, self.update_player_progress)
        else:
            self.stop_audio()

    def conv_wem(self, file):
        # first run ww2ogg
        exe_path = path.join(self.settings['toolPath'], 'ww2ogg', 'ww2ogg.exe')
        # this will run the conversion process on the specified wem file
        args = [exe_path , file, '--pcb', path.join(self.settings['toolPath'], 'ww2ogg', 'packed_codebooks_aoTuV_603.bin')]
        subprocess.call(args = args)
        # now run revorb on thr produced ogg file:
        exe_path = path.join(self.settings['toolPath'], 'revorb', 'revorb.exe')
        args = [exe_path, '{}.ogg'.format(path.splitext(file)[0])]
        subprocess.call(args = args)
        # now we should have a file in the same folder as the file was originally in
        
        
    def getPaths(self):
        self.getAudioPath()
        self.getAdditionPath()
        self.getOutputPath()

    def getAudioPath(self):
        # get the user to specify the audio path
        path = filedialog.askdirectory(title = "Select the path to your AUDIO folder")
        self.settings['audioPath'] = path
        # save the programs' settings to the settings file
        with open('settings.pkl', 'wb') as f:
            pickle.dump(self.settings, f)

    def getOutputPath(self):
        # get the user to specify the output path
        path = filedialog.askdirectory(title = "Select the path to your output folder")
        self.settings['outputPath'] = path
        # save the programs' settings to the settings file
        with open('settings.pkl', 'wb') as f:
            pickle.dump(self.settings, f)

    def getAdditionPath(self):
        # get the user to specify the audio path
        path = filedialog.askdirectory(title = "Select the path to the folder containing additional files.")
        self.settings['additionPath'] = path
        # save the programs' settings to the settings file
        with open('settings.pkl', 'wb') as f:
            pickle.dump(self.settings, f)

    def quit(self):
        print(self.settings)
        if self.player is not None:
            self.player.pause()
        with open('settings.pkl', 'wb') as f:
            pickle.dump(self.settings, f)
        self.master.destroy()      

app = GUI(master = root)
app.mainloop()
