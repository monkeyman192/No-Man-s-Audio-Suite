# program to pack a number of .wem files into a .bnk file

from struct import pack, unpack
from fnvhash import fnvhash
from os import walk, path, mkdir, listdir, makedirs
from collections import OrderedDict as Odict
from io import BytesIO

"""
.bnk file structure
			Header:
Location:		Size:		Type:		Value:		What it is:
+0x000			0x4			char		BKHD		header tag
+0x004			0x4			int			-			size of header, from next 4 bytes (0x008)
+0x008			0x4			int			0x78		version maybe?
+0x00C			0x4			int			-			sound bank ID (hashed version of name)
+0x010			0x8			padding		empty		not used?
+0x018			0x4			int			0x0447		unknown (everything has it)
+0x01C			0x0-0x8		padding		empty		NMS_AUDIO_PERSISTENT has 0x0, intro music are 0x8

			Data Index:
+0x000			0x4			char		DIDX		data index tag
+0x004			0x4			int			-			size of DIDX (multiple of 0xC)
				Data Index Entry (0xC chunks):
+0x000			0x4			int			-			audio file id (hashed version of name)
+0x004			0x4			int			-			relative file offset from start of DATA, 16 bytes aligned
+0x008			0x4			int			-			file size


"""

class BNK():
    def __init__(self, name, source, output_path, mode='extract', counter = None):
        self.name = name
        self.source = source        # this is a path pointing to either the path where all the wems are for recompilation, or the bank to be extracted
        self.output_path = output_path      # the path that the wem's will be extrcted to, or the recompiled bnk will be written to

        self.counter = counter

        if mode == 'extract':
            self.extract()
        else:
            self.included_wems = Odict()
            self.included_hircs = Odict()

            # create a list of all the .wem files in the source directory:
            for root, dirs, files in walk(self.source):
                for file in files:
                    name = path.splitext(file)[0]
                    if path.splitext(file)[1] == '.wem':
                        self.included_wems[name] = path.join(self.source, file)
                    if path.splitext(file)[1] == '.hirc':
                        self.included_hircs[name] = path.join(self.source, file)

            #for key in self.included_wems:
            #    print(key)

            self.num_wems = len(self.included_wems)        # for later

            self.recompile()

    def extract(self):
        # first, let's create an output directory
        if not path.exists(self.output_path):
            makedirs(self.output_path)

        # next, open the bnk and extract what we need
        if self.source == '':
            # this will probably be depreciated
            _input = '{}.BNK'.format(self.name)
        else:
            _input = self.source
        with open(_input, 'rb') as self.input:
            cont = True     # tag to check whether or not to keep going
            while cont == True:
                tag, data = self.read_bnk_chunk()
                if tag == None:
                    cont = False
                else:
                    # we don't actually need to do anything about the header
                    if tag == 'DIDX':
                        self.wem_sizes = Odict()        # use an ordered dict and use the id's as the keys, and the values are the sizes
                        self.wem_offsets = []           # list of the offsets of each wem (to save having to get the length and padding it. We get the data anyway, might as well use it...)
                        self.read_dataindex(data)
                    elif tag == 'DATA':
                        self.read_data(data)
                    elif tag == 'HIRC':
                        with open(path.join(self.output_path, '{}.hirc'.format(self.name)), 'wb') as hirc_file:
                            hirc_file.write(data.read())
                    print(tag)

    def recompile(self):
        if self.output_path == '':
            # this will probably be depreciated
            _output = '{}.BNK'.format(self.name.upper())
        else:
            _output = self.output_path
        with open(_output, 'wb') as self.output:
            self.write_header()
            self.write_dataindex()
            self.write_data()
            self.write_hirc()

    @staticmethod
    def align16(x):
        # this will take any number and round it up to the nearest number that is divisible by 16
        rem = x %16
        return x + (16 - rem)

    def read_bnk_chunk(self):
        # this will read the tag at the current location in self.input, and then return the data and tag
        try:
            tag = self.input.read(4).decode()
            size = unpack('<I', self.input.read(4))[0]
            return [str(tag), BytesIO(self.input.read(size))]
        except:
            # default empty return, telling the program that the end of the file has been reached
            return [None, None]

    def read_dataindex(self, data):
        size = data.getbuffer().nbytes
        num = int(size/0xC)     # each block is 0xC long...
        for i in range(num):
            # for each file, get the ids and sizes of each of the wems
            wem_id = int(unpack('<I', data.read(4))[0])
            self.wem_offsets.append(int(unpack('<I', data.read(4))[0]))
            wem_size = int(unpack('<I', data.read(4))[0])
            self.wem_sizes[wem_id] = wem_size       # update the dict

    def read_data(self, data):
        i = 0
        for wem_id in self.wem_sizes:
            if self.counter is not None:
                self.counter.set(i + 1)
            # move the cursor to the current offset (relative to the start of the data chunk)
            data.seek(self.wem_offsets[i])
            wem_size = self.wem_sizes[wem_id]

            # now, read the actual wem data
            wem_data = data.read(wem_size)
            # ... and write to a file
            with open(path.join(self.output_path, '{}.wem'.format(wem_id)), 'wb') as wem_file:
                wem_file.write(wem_data)
            
            i += 1

    def write_header(self):
        self.output.write(pack('4s', b'BKHD'))                     # header tag
        if self.name != 'NMS_AUDIO_PERSISTENT':              # header size (I am being lazy)
            self.output.write(pack('<i', 0x1C))
        else:
            self.output.write(pack('<I', 0x14))
        self.output.write(pack('<I', 0x78))             # version
        self.output.write(pack('<I', fnvhash(self.name)))   #ID
        self.output.write(pack('8s', b''))     # 0x8 padding
        self.output.write(pack('<I', 0x447))                # unknown
        if self.name != 'NMS_AUDIO_PERSISTENT':
            self.output.write(pack('{}s'.format(0x8), b'')) # 0x8 padding

    def write_dataindex(self):
        self.output.write(pack('4s', b'DIDX'))                  # dataindex tag
        self.output.write(pack('<I', self.num_wems*0xC))        # size of dataindex section
        curr_write_location = 0
        counter = 1
        for file in self.included_wems:
            filesize = path.getsize(self.included_wems[file])
            self.output.write(pack('<I', int(file)))                 # file id
            self.output.write(pack('<I', curr_write_location))  # relative offset
            self.output.write(pack('<I', filesize))             # filesize (un-padded)
            if counter != self.num_wems:
                curr_write_location += self.align16(filesize)
            else:
                curr_write_location += filesize
            counter += 1
        self.total_data_size = curr_write_location
            

    def write_data(self):
        self.output.write(pack('4s', b'DATA'))                  # data tag
        self.output.write(pack('<I', self.total_data_size))     # data size
        counter = 1
        for file in self.included_wems:
            if self.counter is not None:
                self.counter.set(counter)
            filesize = path.getsize(self.included_wems[file])
            if counter != self.num_wems:
                file_padding = self.align16(filesize) - filesize
            else:
                file_padding = 0
            with open(self.included_wems[file], 'rb') as data:
                self.output.write(data.read())
            if file_padding != 0:
                self.output.write(pack('{}s'.format(file_padding), b''))
            counter += 1

    def write_hirc(self):
        # get the total length of all included hirc files
        new_hirc_size = 0
        for hirc in self.included_hircs:
            new_hirc_size += path.getsize(self.included_hircs[hirc])
        self.output.write(pack('4s', b'HIRC'))
        self.output.write(pack('<I', new_hirc_size))
        for hirc in self.included_hircs:
            with open(path.join(self.source, '{}.hirc'.format(hirc)), 'rb') as hirc_file:
                self.output.write(hirc_file.read())

    def hirc(self):
        pass

class HIRC():
    # structs for any required HNRC types. numbers correspond to identifier from http://wiki.xentax.com/index.php/Wwise_SoundBank_(*.bnk)

    # all the static methods take the data of approprtiate length and then parse it
    
    @staticmethod
    def _02_read(data):
        object_id = unpack('<I', data.read(4))
        unknown01 = unpack('<I', data.read(4))      # unused/unknown
        isstreamed = unpack('B', data.read(1))
        audiofile_id = unpack('<I', data.read(4))
        something = unpack('<I', data.read(4))
        empty = unpack('<I', data.read(4))
        

    @staticmethod
    def _04_read(data):
        event_id = unpack('<I', data.read(4))[0]
        num_actions = unpack('B',data.read(1))[0]
        action_event_ids = []
        for event in range(int_num_actions):
            actions_event_ids.append(unpack('<I', data.read(4)[0]))

    @staticmethod
    def _04_write(data, output):
        output.write(pack('<I', data['event_id']))
        output.write(pack('B', data['num_actions']))
        for event_id in data['actions_event_ids']:
            output.write(pack('<I', event_id))
        
        

#HIRC._02()
            
if __name__ == "__main__":
    b = BNK('NMS_AUDIO_PERSISTENT', './bloop', './bloop', 'extract')
