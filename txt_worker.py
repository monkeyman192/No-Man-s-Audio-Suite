# file containing the text worker that combines the text files used to describe audio files in NMS

from os import remove, rename

class txt_worker():
    """ this needs to be re-written
    Since the NMS_AUDIO_PERSISTENT.txt file has lots of other stuff in it, the current implementation well get rid of all that
    A better way to do it will be to try and insert the new data into the file.

    Outline of how to do this:
    - read old file, determining what environment we are in.
    If we are in an environment we want to add stuff to, then iterate through each line
    and if we come across the line we need to insert the data to we insert and keep going.
    This way we will keep all the original data and just insert the new data.
    Should also make all the below code way less extraneous...
    """
    
    def __init__(self, _in, _out):
        self._in = _in
        self._out = _out

        self.in_data = dict()
        self.in_data_ids = dict()

        # first, read the input file and put all the info into 2 dictionaries with the required info.
        self.get_input_data()
        self.merge()
        """
        # first, read all the important data from the input file to be merged into _out
        self.read_txt('in')
        # also get this data for the output file so that we can merge the two lists later
        self.read_txt('out')

        # rename self._out to add an _old on the end of the name
        shutil.move(self._out, '{}_old'.format(self._out))

        self.merge_data()

        self.write_txt()
        """

    def get_input_data(self):
        # reads the input file and reads all the data into a dictionary with keys being the sections
        curr_section = None
        with open(self._in, 'r') as file:
            for line in file:
                if line[0] != '\t' and line[0] != '\n':
                    curr_section = line[:line.index('ID')].rstrip('\t')
                    self.in_data[curr_section] = dict()
                    self.in_data_ids[curr_section] = list()
                elif line[0] != '\n':
                    ID = self.getID(line)
                    self.in_data[curr_section][ID] = line
                    self.in_data_ids[curr_section].append(ID)
        print(self.in_data)
        print(self.in_data_ids)

    def merge(self):
        """ main function to merge two text files """
       
        curr_section = None
        with open('{}_new'.format(self._out), 'w') as new_out:
            with open(self._out, 'r') as old_out:
                for line in old_out:
                    if line[0] != '\t' and line[0] != '\n':
                        #print(line)
                        curr_section = line[:line.index('ID')].rstrip('\t')
                        new_out.write(line)
                        try:
                            curr_next_ID = self.in_data_ids[curr_section][0]
                        except:
                            curr_next_ID = None
                        curr_index = 0
                    elif line[0] != '\n':
                        # this is where we need to find out what the ID is, and if one of the new values in this section lies within, add that line

                        # if the next ID is none, then we do not need to add anything
                        if curr_next_ID == None:
                            new_out.write(line)
                        # otherwise, check to see if the new data to be written is next, or if it is still the old data
                        else:
                            lineID = self.getID(line)
                            if lineID < curr_next_ID:
                                new_out.write(line)
                            else:
                                new_out.write(self.in_data[curr_section][curr_next_ID])
                                new_out.write(line)
                                curr_index += 1
                                try:
                                    curr_next_ID = self.in_data_ids[curr_section][curr_index]
                                except:
                                    curr_next_ID = None
                    else:
                        new_out.write(line)
        # now clean up. Delete the old input in the output folder, and rename the file that ends with _new
        remove(self._out)
        rename('{}_new'.format(self._out), self._out)

    @staticmethod
    def getID(line):
        # this will take a line and return the ID of it
        line = line.lstrip('\t')
        ID = int(line[:line.index('\t')])
        return ID

    def merge_data(self):
        # merges the data and sorts it
        self.events = self.in_events + self.out_events
        for e in self.events:
            try:
                int(e[1])
            except:
                print(e)
        self.events.sort(key = lambda lst: int(lst[1]))
        self.im_audios = self.in_im_audios + self.out_im_audios
        self.im_audios.sort(key = lambda lst: int(lst[1]))
        self.s_audios = self.in_s_audios + self.out_s_audios
        self.s_audios.sort(key = lambda lst: int(lst[1]))

        self.contains_data = {'Event': len(self.events) != 0, 'Streamed': len(self.s_audios) != 0, 'In Memory': len(self.im_audios) != 0}

        #print(self.contains_data)
        

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
                    if curr_data != None:
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
                else:
                    curr_data = None
        #print(self.__dict__['{}_events'.format(mode)])

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


if __name__ == '__main__':
    a = txt_worker('scarytest.txt', 'NMS_AUDIO_PERSISTENT.TXT')
