# program to pack a number of .wem files into a .bnk file

from struct import pack, unpack
from struct import error as struct_error
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
    def __init__(self, name, source, output_path, counter = None):
        self.name = name
        self.source = source        # this is a path pointing to either the path where all the wems are for recompilation, or the bank to be extracted
        self.output_path = output_path      # the path that the wem's will be extrcted to, or the recompiled bnk will be written to

        self.counter = counter      # this is set as a IntVar() by the gui to allow for progress tracking

    def extract(self, specific_ids = [], speedmode = False):
        """This is the function that controls the extraction of the wem's and other data from the .bnk
        There are a few parameters this function can be given:
        - specific_ids:
          This is a list of id's that are to extracted specifically instead of all (which is the default of an empty list)
        - speedmode:
          If set to True, then the data is extracted in a bulk format to allow for far swifter extraction/recompilation
          This is mainly used when just adding streamed files, so only HIRC data needs to be changed
        """
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
                    if speedmode == False:
                        # in this case just extract everything as normal.
                        # we don't actually need to do anything about the header
                        if tag == 'DIDX':
                            self.wem_sizes = Odict()        # use an ordered dict and use the id's as the keys, and the values are the sizes
                            self.wem_offsets = []           # list of the offsets of each wem (to save having to get the length and padding it. We get the data anyway, might as well use it...)
                            self.read_dataindex(data)
                        elif tag == 'DATA':
                            self.read_data(data, specific_ids)
                        elif tag == 'HIRC':
                            # always write the HIRC data.
                            with open(path.join(self.output_path, '{}.hirc'.format(self.name)), 'wb') as hirc_file:
                                hirc_file.write(data.read())
                    else:
                        # in this case, just write all the data in a chunk.
                        if tag == 'DIDX':
                            with open(path.join(self.output_path, '{}.didx'.format(self.name)), 'wb') as didx_file:
                                didx_file.write(data.read())
                        elif tag == 'DATA':
                            with open(path.join(self.output_path, '{}.data'.format(self.name)), 'wb') as data_file:
                                data_file.write(data.read())
                        elif tag == 'HIRC':
                            with open(path.join(self.output_path, '{}.hirc'.format(self.name)), 'wb') as hirc_file:
                                hirc_file.write(data.read())

    def recompile(self):
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

    def read_data(self, data, specific_ids):
        i = 0
        for wem_id in self.wem_sizes:
            if self.counter is not None:
                self.counter.set(i + 1)
            # move the cursor to the current offset (relative to the start of the data chunk)
            data.seek(self.wem_offsets[i])
            wem_size = self.wem_sizes[wem_id]

            # now, read the actual wem data
            if len(specific_ids) != 0:
                if wem_id in specific_ids:
                    wem_data = data.read(wem_size)
                    # ... and write to a file
                    with open(path.join(self.output_path, '{}.wem'.format(wem_id)), 'wb') as wem_file:
                        wem_file.write(wem_data)
            else:
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
        # write the header
        self.output.write(pack('4s', b'HIRC'))
        counter = 0
        for hirc in self.included_hircs:
            if counter == 0:
                new_hirc = HIRC(self.included_hircs[hirc])
                counter += 1
            else:
                new_hirc += HIRC(self.included_hircs[hirc])
        new_hirc_size = new_hirc.data.getbuffer().nbytes
        self.output.write(pack('<I', new_hirc_size))
        self.output.write(new_hirc.data.getbuffer())




class BNK_new():
    def __init__(self, path = None, data = None, entries = None):
        if path is not None:
            with open(path, 'rb') as _input:
                self.data = Odict()
                # first, let's just make sure we have been given a BNK file:
                if unpack('4s', _input.read(4))[0] == b'BKHD':
                    # yep, we *should* be good...
                    _input.seek(0)      # return to start
                    # we go through the rest of the data and populate self.data
                    self.cont = True     # tag to check whether or not to keep going
                    while self.cont == True:
                        self.read_bnk_chunk(_input)
        print(self.data)

        for key in self.data:
            print(key, len(self.data[key]))

    def __add__(self, other):
        combined_didx = self.data['DIDX'] + other.data['DIDX']
        combined_data = self.data['DATA'] + other.data['DATA']
        combined_hirc = self.data['HIRC'] + other.data['HIRC']

        return BNK_new(data = {'BKHD': self.data['BKHD'],
                               'DIDX': combined_didx,
                               'DATA': combined_data,
                               'HIRC': combined_hirc})

    def save(self, path):
        # saves the current bnk files to disc (at location path)
        with open(path, 'wb') as output:
            for key in self.data:
                output.write(self.data[key].getdata())

    def read_bnk_chunk(self, _input):
        # this will read the tag at the current location in self.input, and then return the data and tag
        try:
            tag = _input.read(4).decode()       # use this over decode to just get the data as binary for convenience when writing later...
            print('tag', tag)
            size = unpack('<I', _input.read(4))[0]
            cls = eval(tag)
            self.data[tag] = cls(data = BytesIO(_input.read(size)))
        except struct_error:
            # break the loop
            self.cont = False
        except NameError:
            # class not defined for the sub section of the BNK...
            print("Class {} doesn't exists...".format(tag.decode()))

class BKHD():
    def __init__(self, data):
        self.data = data
        self.tag = b'BKHD'

    def __len__(self):
        return len(self.data.getvalue())

    def getdata(self):
        # ignore all arguments...
        return self.tag + pack('<I', len(self)) + self.data.getvalue()

class DIDX():
    """
    Data Index Entry (0xC chunks):
    +0x000			0x4			int			-			audio file id (hashed version of name)
    +0x004			0x4			int			-			relative file offset from start of DATA, 16 bytes aligned
    +0x008			0x4			int			-			file size
    """
    def __init__(self, data):
        self.tag = b'DIDX'
        self.data = data            # this is a BytesIO object

        # the following two Odict's contain all the data here really once it is serialised back. Maybe better to just store it here and delete self.data?
        self.wem_sizes = Odict()        # use an ordered dict and use the id's as the keys, and the values are the sizes
        self.wem_offsets = Odict()

        self.num_entries = int(len(self)/0xC)     # each block is 0xC long...
        for i in range(self.num_entries):
            # for each file, get the ids and sizes of each of the wems
            wem_id = int(unpack('<I', self.data.read(4))[0])
            self.wem_offsets[wem_id] = int(unpack('<I', self.data.read(4))[0])
            wem_size = int(unpack('<I', self.data.read(4))[0])
            self.wem_sizes[wem_id] = wem_size       # update the dict

        # read off the offset of the final data entry in DATA, and it's size and add together
        # this is the total size of the self.data chunk in the DATA section
        self.data_size = self.wem_offsets[next(reversed(self.wem_offsets))] + self.wem_sizes[next(reversed(self.wem_sizes))]

    def __len__(self):
        return len(self.data.getvalue())

    def __add__(self, other):
        # we will need to adjust all the data here since it will all become re-ordered due to merging with another file
        total_data = self.data + other.data
        # combine the two ordered dicts for each DIDX section
        new_wem_sizes = Odict(self.wem_sizes)
        new_wem_sizes.update(other.wem_sizes)
        new_wem_offsets = Odict(self.wem_offsets)
        new_wem_offsets.update(other.wem_offsets)

        # now we need to do some stuff...
        # first, we need to sort both ordered dicts by key
        sorted_wem_sizes = Odict(sorted(new_wem_sizes.items()))
        del new_wem_sizes       # let's delete it to save memory...
        sorted_wem_offsets = Odict(sorted(new_wem_offsets.items()))
        del new_wem_offsets

        # next is a bit more tricky... We need to calculate the new offsets based on the sizes of the data.
        # the tricky part is that it needs to include the offset so that each one starts as a multiple of 0x10...
        
        return DIDX(total_data)

    def getdata(self):
        return self.tag + pack('<I', len(self)) + self.data.getvalue()
        

class DATA():
    def __init__(self, data):
        self.tag = b'DATA'
        self.data = data

    def __len__(self):
        return len(self.data.getvalue())

    def __add__(self, other):
        # Need to be careful here. We cannot simply add the two data's together as we require some padding between...
        
        self.output.write(pack('{}s'.format(file_padding), b''))

    def getdata(self):
        return self.tag + pack('<I', len(self)) + self.data.getvalue()
        

class HIRC():
    """
    This is a class to load an HIRC file into that will allow it to be merged (and maybe in the future more...)

    HIRC section specification:
    +0x000 - length of section (int)
    +0x004 - number of objects (int)    <- this is the first value in data.
    
    """
    def __init__(self, data):
        self.tag = b'HIRC'
        self.data = data
        self.entries = unpack('<I', data.read(4))[0]
        self.data = BytesIO(self.data.read())        # this will make the data be everything except the first 4 bytes which are the amount of HIRC entries. Not sure if there is a better way?

    def save(self, path):           # this will become redundant soon...
        # save the hirc data as a .hirc file
        with open(path, 'wb') as _output:
            _output.write(pack('<I', self.entries))
            _output.write(self.data)

    def __len__(self):
        return len(self.data.getvalue()) + 4            # we need a + 4 to take into account of the number of entries field (4 byte int)

    def __add__(self, other):
        total_entries = self.entries + other.entries
        total_data = self.data.getvalue() + other.data.getvalue()
        return HIRC(None, total_data, total_entries)

    def getdata(self):
        # return all the data and header of the section
        return self.tag + pack('<I', len(self)) + pack('<I', self.entries) + self.data.getvalue()       # tag, size of HIRC section, number of entries, and then data respectively
        
class WEM():
    def __init__(self, data):
        self.__slots__ = ['data']
        self.data = data


class HIRC_old():
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
        

def align16(x):
    # this will take any number and find the number required to be added to make it divisible by 16 (ie. find 16 - x %16)
    return 16 - (x % 16)

#HIRC._02()
            
if __name__ == "__main__":
    #b = BNK('NMS_AUDIO_PERSISTENT', './bloop', './bloop', 'extract')
    #h = HIRC('SCARYTEST.HIRC')
    #n = HIRC('NMSAP.HIRC')
    #p = h + n
    #p.save('MERGED.HIRC')
    a = BNK_new(path = 'NMS_AUDIO_PERSISTENT.BNK')
    #a.save('newbnk.bnk')
