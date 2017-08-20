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
from os import path, chdir, remove, walk, listdir
import subprocess
import shutil
import threading

# play audio
#import pyglet

from collections import OrderedDict

root = Tk()

import xml.etree.ElementTree as ET

from BNKcompiler import *

DEFAULTSETTINGS = {'audioPath': "",
                   'additionPath': "TO_ADD",
                   'outputPath': "OUTPUT",
                   'workingPath': "TEMP"}
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

class GUI(Frame):
    def __init__(self, master):
        self.master = master
        Frame.__init__(self, self.master)

        self.textFont = font.Font(self, "Calibiri", "12")

        self.SoundBanksData = []     # this will hold all the soundbank Element objects that can be read from directly

        self.selectedAudioListType = 'Str'      # other possibilities: 'Inc' and 'Act'

        # progress bar stuff:
        self.num_files = 100
        self.curr_progress = IntVar()

        # create all the widgets
        self.createWidgets()
        self.createMenus()

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
        print(self.settings)

        if not path.exists(self.settings['audioPath']):
            messagebox.showwarning("Bad Paths!", message = "Paths in settings are incorrect. Please reset!")
            self.getPaths()

        self.generateSoundBankData()

        # populate the list of soundbanks
        self.populateSoundBankList()

    def createWidgets(self):
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
        s_ysb = ttk.Scrollbar(StreamedListFrame, orient=VERTICAL, command=self.StreamedListView.yview)
        s_ysb.pack(side=RIGHT, fill=Y)
        self.StreamedListView.configure(yscroll=s_ysb.set)
        self.StreamedListView.pack(fill=BOTH, expand=YES)
        StreamedListFrame.pack(fill=BOTH, expand=YES)
        if self.selectedAudioListType == 'Str':
            self.StreamedFrame.pack(fill=BOTH, expand=YES)

        self.searchFrame = Frame(self.AudioFrame)
        sortLabel = Label(self.searchFrame, text = "Search: ")
        sortLabel.pack(side = LEFT)
        self.SoundsSortEntry = Entry(self.searchFrame)
        self.SoundsSortEntry.pack(side = LEFT)
        self.progbar = ttk.Progressbar(self.searchFrame, maximum=self.num_files, variable=self.curr_progress)
        self.progbar.pack(side = LEFT)
        self.searchFrame.pack()

        self.AudioFrame.pack(fill=BOTH, expand=YES, side = LEFT)

        # panel for buttons to run various functions
        self.AudioButtonFrame = Frame(self.ListFrame)
        self.unpack_button = Button(self.AudioButtonFrame, text = "Unpack", command = self.unpack_soundbank_threaded)
        self.unpack_button.pack()
        self.repack_button = Button(self.AudioButtonFrame, text = "Repack", command = self.repack_soundbank_threaded)
        self.repack_button.pack()
        self.add_button = Button(self.AudioButtonFrame, text = "Add", command = self.add_audio, state = DISABLED)
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
            self.add_button.config(state = DISABLED)
            if self.selectedAudioListType == 'Inc':
                self.replace_button.config(state = DISABLED)
            else:
                self.replace_button.config(state = NORMAL)
        # always have the replace button disabled for actions
        if self.selectedAudioListType == 'Act':
            self.replace_button.config(state = DISABLED)

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
        self.selectedAudioListType = 'Str'
        self.StreamedFrame.pack(fill=BOTH, expand=YES)
        self.searchFrame.pack()
        self.checkButtonStates()

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
        self.selectedAudioListType = 'Act'
        self.ActionFrame.pack(fill=BOTH, expand=YES)
        self.searchFrame.pack()
        self.checkButtonStates()

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
        self.selectedAudioListType = 'Inc'
        self.IncludedFrame.pack(fill=BOTH, expand=YES)
        self.searchFrame.pack()
        self.checkButtonStates()

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

    def SearchAudioList(self, term, lst, tview):
        # this will search through the list lst for any names containing the string 'term', and return that list
        # we will also need to get the treeview to update
        pass

    @staticmethod
    def getEvents(soundbank):
        IncludedEvents = soundbank.find('IncludedEvents')
        return IncludedEvents.findall('Event')

    @staticmethod
    def getStreamed(soundbank):
        ReferencedStreamedFiles = soundbank.find('ReferencedStreamedFiles')
        return ReferencedStreamedFiles.findall('File')

    @staticmethod
    def getIncluded(soundbank):
        IncludedMemoryFiles = soundbank.find('IncludedMemoryFiles')
        return IncludedMemoryFiles.findall('File')
    
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

    def populateSoundBankList(self):
        # this will populate the soud bank list with all the names
        for sb in self.SoundBanksData:
            name = sb.find('ShortName').text
            if name == 'Vocal_Localised':
                region = sb.find('Path').text.split('\\')[0]
                name = '{0}_[{1}]'.format(name, region)
            if name == 'NMS_Audio_Persistent':
                self.SoundBanksListView.insert("", 0, values=name)
            if name not in ["Init", "ConvVerb_Impulses"]:
                self.SoundBanksListView.insert("", "end", values=name)
            
    def populateActionList(self):
        # this will find what sound bank is selected and populate the action list with the list of actions in the bank

        # first clear the list
        self.ActionListView.delete(*self.ActionListView.get_children())

        # now get the info and populate
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        for event in self.getEvents(soundbank):
            self.ActionListView.insert("", "end", values=event.attrib["Name"])

    def populateStreamedList(self):
        # this will find what sound bank is selected and populate the action list with the list of actions in the bank

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
            self.StreamedListView.insert("", "end", values=[event.find("ShortName").text, event.attrib['Id']])

    def populateIncludedList(self):
        # this will find what sound bank is selected and populate the action list with the list of actions in the bank

        # first clear the list
        self.StreamedListView.delete(*self.StreamedListView.get_children())

        # now get the info and populate
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        for event in self.getIncluded(soundbank):
            self.IncludedListView.insert("", "end", values=[event.find("ShortName").text, event.attrib['Id']])

    def unpack_soundbank_threaded(self):
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        lst = self.getIncluded(soundbank)
        if lst is not None:
            num_files = len(lst)
        else:
            num_files = 0
        #self.num_files = num_files
        self.progbar['maximum'] = num_files
        unpack_thread = threading.Thread(target = self.unpack_soundbank)
        unpack_thread.start()

    def unpack_soundbank(self):
        sb_name = self.getSelectedSoundbankName()
        soundbank = self.searchSoundBanks(sb_name)
        # get the actual path of the soundbank itself, and then move it into the APPSPATH
        soundbank_path = path.join(self.settings['audioPath'], soundbank.find('Path').text.upper())
        BNK(sb_name.upper(), soundbank_path, path.join(self.settings['workingPath'], sb_name.upper()),  mode = 'extract', counter = self.curr_progress)
        self.checkButtonStates()

    def repack_soundbank_threaded(self):
        repack_thread = threading.Thread(target = self.repack_soundbank)
        repack_thread.start()

    def repack_soundbank(self):
        # we need to do a few things here
        # first, get selected soundbank:
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
        BNK(sb_name.upper(), path.join(self.settings['workingPath'], sb_name.upper()), output_path, mode = 'recompile', counter = self.curr_progress)

    def add_audio(self):
        pass
        """
        # get the name of the currently selected bank
        sb_name = self.getSelectedSoundbankName()
        #soundbank = self.searchSoundBanks(sb_name)
        
        add_path = self.settings['additionPath']
        working_path = self.settings['workingPath']
        # copy the required files from the AUDIO folder:
        shutil.copy(path.join(self.settings['audioPath'], "{}.TXT".format(sb_name)), working_path)
        shutil.copy(path.join(self.settings['audioPath'], "{}.XML".format(sb_name)), working_path)
        shutil.copy(path.join(self.settings['audioPath'], "SOUNDBANKSINFO.XML"), working_path)
        for folder in listdir(add_path):
            proj_path = path.join(add_path, folder)
            print(proj_path)

            # first, let's extract the HIRC info from the BNK:
            BNK('scarytest', path.join(proj_path, 'scarytest.bnk'), working_path, mode = 'extract')

        # merge the wwise generated and original txt files
        txt_worker(path.join(add_path, 'scarytest', 'scarytest.txt'), path.join(working_path, "{}.TXT".format(sb_name)))

        # merge the wwise generated soundbanksinfo.xml file into the soundbanksinfo and original xml files
        xml_worker(path.join(add_path, 'scarytest', 'SoundbanksInfo.xml'), path.join(working_path, "{}.XML".format(sb_name)), sb_name, ignore_streamed = True)
        xml_worker(path.join(add_path, 'scarytest', 'SoundbanksInfo.xml'), path.join(working_path, "SOUNDBANKSINFO.XML"), sb_name)
        """

    def getSelectedSoundbankName(self):
        iid = self.SoundBanksListView.focus()
        return self.SoundBanksListView.item(iid)['values'][0]

    @staticmethod
    def getSelectedAudioId(tview):
        # get the ID of the selected audio event (will only work for streamed or included audios)
        iid = tview.focus()
        return tview.item(iid)['values'][1]

    @staticmethod
    def highlightSelectedAudioId(tview):
        # whatever element in the list is selected, highlight it (change background)
        tview.item(tview.focus(),  tag = 'modified')

    def replace_audio(self):
        out_path = self.settings['outputPath']
        working_path = self.settings['workingPath']
        # we'll get the user to specify the file:
        replacement_file = filedialog.askopenfilename(title = "Select the audio to use as replacement")
        print(replacement_file)
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
        with open('settings.pkl', 'wb') as f:
            pickle.dump(self.settings, f)
        self.master.destroy()

class txt_worker():
    def __init__(self, _in, _out):
        self._in = _in
        self._out = _out

        self.in_events = []
        self.in_s_audios = []
        self.in_im_audios = []
        self.out_events = []
        self.out_s_audios = []
        self.out_im_audios = []

        # first, read all the important data from the input file to be merged into _out
        self.read_txt('in')
        # also get this data for the output file so that we can merge the two lists later
        self.read_txt('out')

        # rename self._out to add an _old on the end of the name
        shutil.move(self._out, '{}_old'.format(self._out))

        self.merge_data()

        self.write_txt()

    def merge_data(self):
        # merges the data and sorts it
        self.events = self.in_events + self.out_events
        self.events.sort(key = lambda lst: int(lst[1]))
        self.im_audios = self.in_im_audios + self.out_im_audios
        self.im_audios.sort(key = lambda lst: int(lst[1]))
        self.s_audios = self.in_s_audios + self.out_s_audios
        self.s_audios.sort(key = lambda lst: int(lst[1]))

        self.contains_data = {'Event': len(self.events) != 0, 'Streamed': len(self.s_audios) != 0, 'In Memory': len(self.im_audios) != 0}

        print(self.contains_data)
        

    def read_txt(self, mode):
        # mode is either 'in' or 'out'
        curr_data = None
        if mode not in ['in', 'out']:
            mode = 'in'     # just set a default
        events = self.__dict__['{}_events'.format(mode)]
        s_audios = self.__dict__['{}_s_audios'.format(mode)]
        im_audios = self.__dict__['{}_im_audios'.format(mode)]
        with open(self.__dict__['_{}'.format(mode)], 'r') as file:
            for line in file:
                if line.startswith('Event'):
                    curr_data = 'Event'
                elif line.startswith('Streamed'):
                    curr_data = 'Streamed'
                elif line.startswith('In Memory'):
                    curr_data = 'In Memory'
                elif len(line) != 1:
                    line_data = line.strip('\n').split('\t')
                    if line_data[-1] == '':
                        del line_data[-1]
                    #self.remove_gaps(line_data)
                    if curr_data == 'Event':
                        events.append(line_data)
                    elif curr_data == 'Streamed':
                        s_audios.append(line_data)
                    elif curr_data == 'In Memory':
                        im_audios.append(line_data)
        print(self.__dict__['{}_events'.format(mode)])

    def write_txt(self):
        dtypes = {'Event': self.events, 'Streamed': self.s_audios, 'In Memory':self.im_audios}
        dtypes_written = {'Event': False, 'Streamed': False, 'In Memory': False}        # whether or not the dtype has been written
        curr_data = None
        curr_data_written = False
        # open both the original output file, and a new one so that we can write unchanged data directly from one into the other
        with open('{}_old'.format(self._out), 'r') as orig_out:
            with open(self._out, 'w') as new_out:
                for line in orig_out:
                    if line[0].isalnum():
                        if line.startswith('Event'):
                            new_out.write(line)
                            curr_data = 'Event'
                            dtypes_written[curr_data] = True
                            curr_data_written = False
                        elif line.startswith('Streamed'):
                            new_out.write(line)
                            curr_data = 'Streamed'
                            dtypes_written[curr_data] = True
                            curr_data_written = False
                        elif line.startswith('In Memory'):
                            new_out.write(line)
                            curr_data = 'In Memory'
                            dtypes_written[curr_data] = True
                            curr_data_written = False
                        else:
                            curr_data = None
                            new_out.write(line)
                    if curr_data != None and curr_data_written != True:
                        for val in dtypes[curr_data]:
                            new_out.write(self.to_output(val))
                        new_out.write('\n')
                        curr_data_written = True
                    elif curr_data_written == False:
                        new_out.write(line)
                # we can now check to make sure that all the dtypes that needed to be written have been written
                for key in dtypes_written:
                    if dtypes_written[key] == False and self.contains_data[key] == True:
                        # in this case the data *should* have been written but hasn't
                        # so write the approriate title part
                        titles = {'Event': "Event\tID\tName\t\t\tWwise Object Path\tNotes\n",
                                  'Streamed': "Streamed Audio\tID\tName\tAudio source file\tGenerated audio file\tWwise Object Path\tNotes\n",
                                  'In Memory': "In Memory Audio\tID\tName\tAudio source file\t\tWwise Object Path\tNotes\tData Size\n"}
                        new_out.write(titles[key])
                        for val in dtypes[key]:
                            new_out.write(self.to_output(val))
                        new_out.write('\n')

    @staticmethod
    def to_output(lst):
        # converts the list data into the string data to be exported
        # this will add a \t' after every element and a \n at the end
        out_string = ''
        for i in lst:
            out_string += i + '\t'
        out_string += '\n'
        return out_string

class xml_worker():
    """ parse the input and output xml files and move all streamed or included audios, and events into the output xml """
    def __init__(self, _in, _out, sb_name, ignore_streamed = False):
        self._in = _in
        self._out = _out
        self.sb_name = sb_name        # name of the sounbank that is having the data written into it (so that we can put the data in the correct place in the SoundbanksInfo.xml file...)
        self.ignore_streamed = ignore_streamed

        self.read_xml_in()
        # we should now have all the needed data in the required places
        # next, open the output xml and write the new data into it
        self.write_xml_out()
        
    def read_xml_in(self):
        self.in_tree = ET.ElementTree()
        self.in_tree.parse(self._in)

        self.in_events = list()
        self.in_ref_s_audios = list()
        self.in_im_audios = list()
        in_s_audios = self.in_tree.find('StreamedFiles').iter('File')
        if in_s_audios is not None:
            self.in_s_audios = list(in_s_audios)

        soundbanks = list(self.in_tree.find('SoundBanks').iter('SoundBank'))
        for sb in soundbanks:
            if sb.find('ShortName') != 'Init':
                sb_events = sb.find('IncludedEvents')
                if sb_events is not None:
                    self.in_events += list(sb_events.iter('Event'))
                sb_ref_s = sb.find('ReferencedStreamedFiles')
                if sb_ref_s is not None:
                    self.in_ref_s_audios += list(sb_ref_s.iter('File'))
                sb_im_audio = sb.find('IncludedMemoryFiles')
                if sb_im_audio is not None:
                    self.in_im_audios += list(sb_im_audio.iter('File'))

    def write_xml_out(self):
        # first, write any streamed files:
        self.out_tree = ET.ElementTree()
        self.out_tree.parse(self._out)
        
        # let's first deal with the stremed files (if any)
        if not self.ignore_streamed:
            self.add_or_append(self.out_tree, 'StreamedFiles', self.in_s_audios)

        # next, get the soundbank node in the output xml
        sbs = list(self.out_tree.find('SoundBanks').iter('SoundBank'))
        req_sb = None
        for sb in sbs:
            if sb.find('ShortName').text == self.sb_name:
                req_sb = sb
        if req_sb is not None:
            # now, we can do all the adding of extra stuff:
            self.add_or_append(req_sb, 'IncludedEvents', self.in_events)
            print(self.ignore_streamed)
            if not self.ignore_streamed:
                self.add_or_append(req_sb, 'ReferencedStreamedFiles', self.in_ref_s_audios)
            else:
                self.add_or_append(req_sb, 'ReferencedStreamedFiles', self.in_s_audios)
            self.add_or_append(req_sb, 'IncludedMemoryFiles', self.in_im_audios)
            
        self.out_tree.write(self._out)

    @staticmethod
    def add_or_append(node, tag, data):
        # this will take a node, a tag, and some data
        # if the tag isn't a sub element of the node it will be added, and the data will be added to it
        # if the tag exists, it simply extends the data
        sf = node.find(tag)
        if sf is not None:
            sf.extend(data)
        else:
            sf = ET.Element(tag)
            sf.extend(data)
            try:
                node.append(sf)
            except AttributeError:
                node.getroot().append(sf)
        
        

app = GUI(master = root)
app.mainloop()
