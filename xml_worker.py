# file containing the xml worker class that is used to combine the xml files that NMS uses to describe the audio format

import xml.etree.ElementTree as ET

class xml_worker():
    """ parse the input and output xml files and move all streamed or included audios, and events into the output xml """
    def __init__(self, _in, _out, sb_name, sbinfo = False):
        self._in = _in
        self._out = _out
        self.sb_name = sb_name        # name of the sounbank that is having the data written into it (so that we can put the data in the correct place in the SoundbanksInfo.xml file...)
        self.isSbInfo = sbinfo                  # whether or not the output file is the SoundBanksInfo file as we need to handle it differently

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
        if self.isSbInfo:
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
            if self.isSbInfo:
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
