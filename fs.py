import cmd, sys
from typing import Optional, TypeVar, Tuple
from abc import ABC
import math
import os.path

NAME_WIDTH = 16
NAME_DOT = "."
NAME_DOT_DOT = ".."

def log_info(x):
    print("INFO:", x)

def log_fail(x):
    print("FAIL:", x)

U = TypeVar('U')

def Optional_unwrap(x: Optional[U]) -> U:
    assert x is not None
    y: U = x
    return y

# working with blocks
BLOCK_SIZE = 64

class Block:
    def __init__(self) -> None:
        self.block: bytearray = bytearray(b'\x00')*BLOCK_SIZE
        self.index = -1

    def write(self, str) -> None:
        self.block = bytearray(str)

class FileDesc(ABC):
    def __init__(self, type) -> None:
        log_info(f"New FileDesc {self}")
        self.type = type # d чи r
        self.nlink = 1 # максимум 16 розрядів
        self.size = 0 # максимум 16 розрядів
        self.nblock = 0 # максимум 16 розрядів
        self.to_delete = 0

    def __del__(self) -> None:
        log_info(f"Del FileDesc {self}")

    def __str__(self) -> str:
        return f"{id(self)} {type(self).__name__}"

class FileReg(FileDesc):
    def __init__(self) -> None:
        super().__init__("r")
        self.data: list[Optional[Block]] = list()
        self.link: int = None

class FileSym(FileDesc):
    def __init__(self, value: str) -> None:
        super().__init__("s")
        self.value: str = value

class FileDir(FileDesc):
    def __init__(self, pardesc: FileDesc = None) -> None:
        super().__init__("d")
        self.links: dict[str, FileDesc] = dict()
        self.links[NAME_DOT] = self
        self.links[NAME_DOT_DOT] = Optional_unwrap(pardesc) \
            if pardesc != None else self

def path_exist(pardir: Optional[FileDir], desc: Optional[FileDesc], \
            path: str) -> bool:
    if pardir == None:
        log_fail(f"Wrong path '{path}'")
        return True
    if desc != None:
        log_fail(f"Link '{path}' already exists")
        return True
    return False

def path_not_exist(pardir: Optional[FileDir], desc: Optional[FileDesc], \
            path: str) -> bool:
    if pardir == None:
        log_fail(f"Wrong path '{path}'")
        return True
    if desc == None:
        log_fail(f"Link '{path}' does not exist")
        return True
    return False

def desc_is_FileDir(desc: FileDesc, path: str) -> bool:
    if not isinstance(desc, FileDir):
        return False
    return True

def str_to_bytes(c):
    c = int(c)
    return c.to_bytes(1, sys.byteorder)

def str_to_binary(c):
    c = str(c)
    return ' '.join(format(ord(i),'b').zfill(8) for i in c)

# format data max length -> 16
MAX_R = 16
def format_data_write_file(n):
    n = str(n)
    n_len = len(n)
    if n_len > MAX_R:
        n = n[0:MAX_R]
    elif n_len < MAX_R:
        n = " " * (MAX_R - n_len) + n
    return str(n)

BLOCKS_MAP_SIZE = 5
DESC_SIZE = 1 + MAX_R + MAX_R + MAX_R + BLOCKS_MAP_SIZE*MAX_R
DESC_NUMBER = 10 # user sets
SUPERBLOCK_SIZE = 48 
BLOCKS_NUMBER = 50 # program sets, depending on file size
HARDLINK_LEN = MAX_R * 2
HARDLINKS_SIZE = DESC_NUMBER * HARDLINK_LEN #depends on user input of desc number

class FS:
    def __init__(self) -> None:
        self.initialized = 0

    def encode_descriptor(self, desc: FileDesc) -> str: 
        block_map = ""
        if (desc.type == 'r'):
            for item in desc.data:
                block_map += format_data_write_file(item.index)
        else:
            block_map = " " * MAX_R * BLOCKS_MAP_SIZE
        return desc.type + format_data_write_file(desc.nlink) + format_data_write_file(desc.size) + format_data_write_file(desc.nblock)  + block_map #last field for map of block numbers

    def encode_hardlink(self, link) -> str:
        name = link[0]
        index = link[1]
        return format_data_write_file(name) + format_data_write_file(index)

    def mkfs(self, n = 10) -> None: 
        self.initialized = 1
        file_size = int(os.path.getsize('fs'))
        global DESC_NUMBER
        DESC_NUMBER = int(n)
        global HARDLINKS_SIZE
        HARDLINKS_SIZE = DESC_NUMBER * HARDLINK_LEN
        global BLOCKS_NUMBER
        BLOCKS_NUMBER = math.floor((file_size - SUPERBLOCK_SIZE - HARDLINKS_SIZE - (DESC_SIZE*DESC_NUMBER))/(BLOCK_SIZE + 1))
        self.superblock = {
            'desc_num': DESC_NUMBER,
            'blocks_num': BLOCKS_NUMBER,
            'blocks_size': BLOCK_SIZE
        }
        self.rootdir: FileDir = FileDir()
        self.blocks: list[Optional[Block]] = [None] * BLOCKS_NUMBER
        self.bitmap: list[int] = [0]*BLOCKS_NUMBER

        # ім'я файлу - 16, номер дескриптора - 16
        self.hardlinks: list[list[str]] = list()
        for i in range(DESC_NUMBER):
            a = list()
            a.append(" ")
            a.append("-")
            self.hardlinks.append(a)
        self.hardlinks[0] = ['.', '0']
        self.hardlinks[1] = ['..', '0']

        # keep track of descriptors and theirs ids
        self.descriptors: list[Optional[FileDesc]] = [FileDesc('-')] * DESC_NUMBER
        self.descriptors[0] = self.rootdir

        # superblock meta takes MAX_R*number_of_fields_in_superblock of space
        superblock_data = ""
        for item in self.superblock.values():
            superblock_data += format_data_write_file(item)

        # hardlinks take descriptors_number*(16+16) of space
        hardlinks_data = ""
        for item in self.hardlinks:
            hardlinks_data += self.encode_hardlink(item)

        descriptors_data = ""
        for desc in self.descriptors:
            descriptors_data += self.encode_descriptor(desc)

        bitmap = "0"*BLOCKS_NUMBER

        blocks_data = ""
        for key in range(len(self.blocks)):
            block = Block()
            self.blocks[key] = block
            block.index = key
            blocks_data += " "*BLOCK_SIZE
        with open("fs", "w+") as file:
            file.write(superblock_data + hardlinks_data + descriptors_data + bitmap + blocks_data)
        self.fs_data()

    def set_hardlinks(self) -> None:
        self.hardlinks: list[list[str]] = list()
        with open('fs', "r") as file:
            for i in range(DESC_NUMBER):
                file.seek(MAX_R * 3 + HARDLINK_LEN*i)
                a = list()
                name = file.read(MAX_R).strip()
                if len(name) == 0:
                    name = " "
                a.append(name)
                file.seek(MAX_R * 3 + HARDLINK_LEN*i + MAX_R)
                index = file.read(MAX_R).strip()
                a.append(index)
                self.hardlinks.append(a)

    def mount(self, fs) -> None:
        self.initialized = 1

        with open(fs, "r") as file:
            n = int(file.read(MAX_R).strip())
            global DESC_NUMBER
            DESC_NUMBER = n
            file.seek(MAX_R)
            global BLOCKS_NUMBER
            BLOCKS_NUMBER = int(file.read(MAX_R).strip())
            blocks_num = BLOCKS_NUMBER
            file.seek(MAX_R * 2)
            global BLOCK_SIZE 
            BLOCK_SIZE = int(file.read(MAX_R).strip())
            global HARDLINKS_SIZE
            HARDLINKS_SIZE = DESC_NUMBER * HARDLINK_LEN

            self.superblock = {
                'desc_num': DESC_NUMBER,
                'blocks_num': blocks_num,
                'blocks_size': BLOCK_SIZE
            }
            self.descriptors: list[Optional[FileDesc]] = [None] * DESC_NUMBER
            self.blocks: list[Optional[Block]] = [None] * blocks_num
            self.bitmap: list[int] = [0]*BLOCKS_NUMBER
            self.set_hardlinks()

            for i in range(blocks_num):
                file.seek(self.get_block_offset(i))
                self.blocks[i] = Block()
                self.blocks[i].write(file.read(BLOCK_SIZE).encode())
                self.blocks[i].index = i

            for i in range(DESC_NUMBER):
                file.seek(self.get_descriptor_offset(i))
                type = file.read(1).strip()
                # directory - only one and the first descriptor
                if type == 'd':
                    self.descriptors[i] = FileDir()
                elif type == 'r':
                    self.descriptors[i] = FileReg()
                elif type == 's':
                    self.descriptors[i] = FileSym()
                else:
                    self.descriptors[i] = FileDesc('-')
                self.descriptors[i].type = type
                file.seek(self.get_descriptor_offset(i) + 1)
                self.descriptors[i].nlink = int(file.read(MAX_R).strip())
                file.seek(self.get_descriptor_offset(i) + 1 + MAX_R)
                self.descriptors[i].size = int(file.read(MAX_R).strip())
                file.seek(self.get_descriptor_offset(i) + 1+2*MAX_R)
                self.descriptors[i].nblock = int(file.read(MAX_R).strip())
                if type == 'r':
                    for j in range(BLOCKS_MAP_SIZE):
                        file.seek(self.get_descriptor_offset(i) + 1+3*MAX_R + (MAX_R)*j)
                        block_num = file.read(MAX_R).strip()
                        if block_num == "":
                            break
                        if j == (BLOCKS_MAP_SIZE - 1):
                            self.descriptors[i].link = 1
                        block_num = int(block_num)
                        block = self.blocks[block_num]
                        self.descriptors[i].data.append(block)
                    if self.descriptors[i].link == 1:
                        block_offset = self.get_block_offset(self.descriptors[i].data[-1].index)
                        file.seek(block_offset)
                        for j in range(int(BLOCK_SIZE/MAX_R)):
                            block_num = file.read(MAX_R).strip()
                            if block_num == "":
                                break
                            block_num = int(block_num)
                            block = self.blocks[block_num]
                            self.descriptors[i].data.append(block)

            for key, value in self.hardlinks:
                if value == '' or value == '-':
                    continue
                value = int(value)
                self.descriptors[0].links[key] = self.descriptors[value]
            self.rootdir: FileDir = self.descriptors[0]

            for i in range(BLOCKS_NUMBER):
                file.seek(self.get_bitmap_offset(i))
                self.bitmap[i] = int(file.read(1))

    def lookup(self, d: FileDir, name: str) -> Tuple[Optional[FileDesc], int]:
        if name in d.links:
            return d.links[name], self.descriptors.index(d.links[name])
        return None, None

    def fs_data(self):
        with open("fs", "r") as file:
            print("Descriptors number: ", file.read(MAX_R).strip())
            file.seek(MAX_R)
            print("Blocks number: ", file.read(MAX_R).strip())
            file.seek(MAX_R*2)
            print("Blocks size: ", file.read(MAX_R).strip())

    def reverse_lookup(self, d: FileDir, desc: FileDesc) -> Optional[str]:
        for name, dest in d.links.items():
            if dest == desc:
                return name
        return None

    def find_free_descriptor(self) -> int:
        descriptors_taken = list()
        for key in range(int(HARDLINKS_SIZE/HARDLINK_LEN)):
            link = self.hardlinks[key]
            if link[1] not in descriptors_taken:
                descriptors_taken.append(link[1].strip())
        for i in range(DESC_NUMBER):
            i = str(i)
            if i not in descriptors_taken:
                return int(i)
        return -1

    def get_hardlink_offset(self, index: int) -> int:
        return SUPERBLOCK_SIZE + HARDLINK_LEN*index

    def get_descriptor_offset(self, index: int) -> int:
        return SUPERBLOCK_SIZE + HARDLINKS_SIZE + DESC_SIZE*index

    def get_bitmap_offset(self, index: int) -> int:
        return SUPERBLOCK_SIZE + HARDLINKS_SIZE + DESC_SIZE*DESC_NUMBER + index

    def get_block_offset(self, index: int) -> int:
        return SUPERBLOCK_SIZE + HARDLINKS_SIZE + DESC_SIZE*DESC_NUMBER + BLOCKS_NUMBER + BLOCK_SIZE*index

    def create(self, d: FileDir, name: str) -> int:
        index = self.find_free_descriptor()
        if index == -1:
            return -1
        desc: FileDir = FileReg()
        d.links[name] = desc
        ind = self.get_free_hardlink()
        if ind == -1:
            return -1
        self.hardlinks[ind][0] = format_data_write_file(name)
        self.hardlinks[ind][1] = format_data_write_file(index)
        h_offset = self.get_hardlink_offset(ind)
        hl_encoded = self.encode_hardlink(self.hardlinks[ind])
        self.descriptors[index] = desc
        desc_encoded = self.encode_descriptor(desc)
        offset = self.get_descriptor_offset(index)
        with open("fs", "r+") as file:
            file.seek(h_offset)
            file.write(hl_encoded)
        with open("fs", "r+") as file:
            file.seek(offset, 0)
            file.write(desc_encoded)
        return 1

    def update_links(self, d: FileDir):
        prev_links_names = list()
        prev_links_desc_nums = list()
        with open("fs", "r+") as file:
            for i in range(DESC_NUMBER):
                links_offset = self.get_hardlink_offset(i)
                file.seek(links_offset)
                file.write(format_data_write_file(" "))
                file.write(format_data_write_file("-"))
                if i < len(d.links):
                    file.seek(links_offset)
                    name = format_data_write_file(list(d.links.keys())[i])
                    desc_num = self.descriptors.index(list(d.links.values())[i])
                    file.write(name)
                    file.write(format_data_write_file(desc_num))
            self.set_hardlinks()         

    def link(self, d: FileDir, name: str, dest: FileDesc) -> None:
        d.links[name] = dest
        dest.nlink += 1
        self.update_links(d)
        self.update_file_data(dest)

    def unlink(self, d: FileDir, name: str, opened: bool) -> None:
        dest = d.links[name]
        if opened == 0:
            dest.nlink -= 1
            del d.links[name]
            hardlink = list([str(name), str(self.descriptors.index(dest))])
            if hardlink in self.hardlinks: 
                self.hardlinks[self.hardlinks.index(hardlink)] = [' ', '-']
            self.update_links(d)
            if dest.nlink == 0:
                self.free_blocks(dest, 0)
        else:
            dest.to_delete = 1

    def get_free_hardlink(self) -> int:
        for i in range(len(self.hardlinks)):
            if self.hardlinks[i][1] == "-":
                return i
        return -1

    def ls(self, d: FileDir, cwd: FileDir) -> None:
        for name, dest in d.links.items():
            print(f"\t{name: <{NAME_WIDTH}} => type={dest.type} desc={self.descriptors.index(dest)}", end = '')
            print()
    
    def read(self, size: int, d: FileReg, offset: int) -> str:
        data_len = d.nblock
        size = int(size)
        if data_len == 0:
            return "File empty"    

        block_index_start = int(abs(offset/BLOCK_SIZE))
        if block_index_start == BLOCKS_MAP_SIZE - 1:
                block_index_start += 1
        if data_len <= block_index_start or offset >= d.size:
            return "Error: Wrong offset!"
        if d.size < size:
            size = d.size
        block_start_offset = offset%BLOCK_SIZE
        block_start = d.data[block_index_start]
        reads = list()
        first_read = self.get_block_characters(d, offset)
        if size < first_read:
            first_read = size
        reads.append(first_read)
        if size > first_read:
            other_reads_num = math.ceil((size - first_read)/BLOCK_SIZE)
            last_read = (size - first_read)%BLOCK_SIZE
            for i in range(other_reads_num):
                reads.append(BLOCK_SIZE)
            if last_read == 0:
                last_read = BLOCK_SIZE
            reads[len(reads) - 1] = last_read
        result = ""
        for read in reads:
            seek_num = self.get_block_offset(d.data[block_index_start].index) + block_start_offset
            with open('fs', "r") as file:
                file.seek(seek_num)
                result += file.read(read).strip()
            block_index_start = block_index_start + 1
            if block_index_start == BLOCKS_MAP_SIZE - 1:
                block_index_start += 1
            if block_index_start >= d.nblock:
                break 
            block_start_offset = 0  
        return result 

    def get_free_block(self) -> int:
        for key in range(len(self.bitmap)):
            if self.bitmap[key] == 0:
                return key
        return -1

    def get_block_characters(self, d: FileReg, offset: int) -> int:
        block_start_offset = offset%BLOCK_SIZE
        return BLOCK_SIZE - block_start_offset

    def update_file_data(self, d: FileReg) -> None: #update file info on block's data change
        #get descriptor index
        index = self.descriptors.index(d)
        desc_offset = self.get_descriptor_offset(index)
        #get curr block number map
        curr_block_number_map = list()
        for block in d.data:
            curr_block_number_map.append(block.index)
        prev_block_map = list()
        if d.link is not None:
            # get block for other block numbers to write into
            index = None
            index_list = curr_block_number_map
            if len(curr_block_number_map) < BLOCKS_MAP_SIZE:
                index = d.temp_last_bl_link[BLOCKS_MAP_SIZE - 1]
                prev_block_map = list() + d.temp_last_bl_link
            else:
                index = index_list[BLOCKS_MAP_SIZE - 1]
            seek_num = self.get_block_offset(index)
            with open('fs', "r+") as file:
                entries_fit = math.floor(BLOCK_SIZE/MAX_R)
                file.seek(seek_num)
                #rewrite all entries
                for index in range(entries_fit):
                    i = BLOCKS_MAP_SIZE + index
                    offset =  seek_num + MAX_R*(index)
                    file.seek(offset)
                    file.write(format_data_write_file(" "))
                    if len(index_list) - 1 < i:
                        if index == 0:
                            d.link = None
                            if len(index_list) == BLOCKS_MAP_SIZE:
                                index_list.pop()
                                d.data.pop()
                            d.nblock -= 1
                        continue
                    num = index_list[i]
                    file.seek(offset)
                    file.write(format_data_write_file(num))
        block_number_map = curr_block_number_map[0:BLOCKS_MAP_SIZE]        
        # update nlink
        nlink_offset = desc_offset + 1
        nlink_data = format_data_write_file(d.nlink)
        #update size
        size_offset = nlink_offset + MAX_R
        d_size = len(curr_block_number_map)
        if d.link is not None:
            d_size -= 1
        d.size = d_size * BLOCK_SIZE
        size_data = format_data_write_file(d.size)
        # update nblock
        nblock_offset = size_offset + MAX_R
        d.nblock = len(curr_block_number_map)
        nblock_data = format_data_write_file(d.nblock)
        #write curr block number map and get prev block number map
        with open('fs', "r+") as file:
            if d.nlink == 0:
                file.seek(desc_offset)
                file.write('-')
            file.seek(nlink_offset)
            file.write(nlink_data)
            file.seek(size_offset)
            file.write(size_data)
            file.seek(nblock_offset)
            file.write(nblock_data)
            for i in range(BLOCKS_MAP_SIZE):
                file.seek(nblock_offset + MAX_R*i + MAX_R)
                curr_block_index = file.read(MAX_R).strip()
                file.seek(nblock_offset + MAX_R*i + MAX_R)
                if curr_block_index != "":
                    prev_block_map.append(int(curr_block_index))
                if i <= len(block_number_map) - 1:
                    file.write(format_data_write_file(block_number_map[i]))
                else:
                    file.write(format_data_write_file(" "))
        # update bitmap
            for i in range(BLOCKS_NUMBER):
                bitmap_offset = self.get_bitmap_offset(i)
                file.seek(bitmap_offset)
                if i in curr_block_number_map:
                    file.write("1")
                    self.bitmap[i] = 1
                file.seek(bitmap_offset)
                if i in prev_block_map and i not in curr_block_number_map:
                    file.write("0")
                    self.bitmap[i] = 0

    def free_blocks(self, desc: FileReg, size: int) -> None:
        blocks_num = size/BLOCK_SIZE
        block_num_curr = desc.nblock
        to_free_blocks_num = block_num_curr - blocks_num
        temp_last_bl_link = list(map(lambda x: x.index, desc.data.copy()))
        for i in reversed(range(block_num_curr)):
            if to_free_blocks_num != 0:
                if i == BLOCKS_MAP_SIZE - 1:
                    desc.temp_last_bl_link = temp_last_bl_link
                del desc.data[i]
                to_free_blocks_num -= 1
        self.update_file_data(desc)

    def write_to_new_block(self, d: FileReg) -> bool:
        index = self.get_free_block()
        if index == -1:
            log_info("No space left!")
            return False
        data_len = len(d.data)
        if data_len == BLOCKS_MAP_SIZE + (BLOCK_SIZE/MAX_R):
            log_info('Maximum file size reached!')
            return
        if data_len + 1 == BLOCKS_MAP_SIZE:
            d.link = index
            self.bitmap[index] = 1
            d.data.append(self.blocks[index])
            index = self.get_free_block()
            if index == -1:
                log_info("No space left!")
                return False
        d.data.append(self.blocks[index])
        self.update_file_data(d)
        return True
        
    def write(self, text: str, d: FileReg, offset: int) -> bool:
        text_len = len(text)
        data_len = d.nblock
        block_index_start = int(abs(offset/BLOCK_SIZE))
        block_start_offset = offset%BLOCK_SIZE
        if block_index_start >= BLOCKS_MAP_SIZE - 1:
            block_index_start += 1
        if data_len <= block_index_start:
            res = self.write_to_new_block(d)
            if not res:
                return False
        block_start = d.data[block_index_start]
        seek_num = self.get_block_offset(block_start.index) + block_start_offset
        with open('fs', "r+") as file:
            file.seek(seek_num, 0)
            file.write(text)
        return True
                    
class OS:
    def __init__(self) -> None:
        self.fs: FS = FS()
        self.fd: list[FileReg] = list()
        self.offsets: list[int] = list()

    def lookup(self, path: str, follow: bool = True) \
                -> Tuple[Optional[FileDir], Optional[FileDesc], str, int]:
        curdir: FileDir = self.fs.rootdir if path[0] == '/' else self.cwd
        pardir: Optional[FileDir] = curdir
        if path == "/":
            return pardir, curdir, "", None
        comp = path.split('/')
        desc = None
        index = None
        for i, name in enumerate(comp):
            if name == "":
                continue
            desc, index = self.fs.lookup(curdir, name)
            if desc is None:
                if i < len(comp) - 1:
                    pardir = None
                break
            desc = Optional_unwrap(desc)
            if isinstance(desc, FileDir):
                curdir = desc
            elif isinstance(desc, FileSym):
                if i == len(comp) - 1 and not follow:
                    break
                if desc.value[0] == '/':
                    curdir = self.fs.rootdir
                comp[i+1:i+1] = desc.value.split('/')
            elif isinstance(desc, FileReg):
                if i != len(comp) - 1:
                    pardir = None
                    desc = None
                break
            if i < len(comp) - 1:
                pardir = curdir
        return pardir, desc, name, index

    def create(self, path: str) -> None:
        log_info(f"Create regular file '{path}'")
        pardir, desc, name, _ = self.lookup(path)
        if path_exist(pardir, desc, path):
            return
        if len(path) > MAX_R:
            log_fail(f"Name '{path}' maximum length is {MAX_R}")
            return

        if len(list(pardir.links.keys())) > DESC_NUMBER:
            log_fail(f"Maximum file quantity reached!")
            return
        self.fs.create(Optional_unwrap(pardir), name)

    def link(self, path1: str, path2: str) -> None:
        log_info(f"Create link '{path2}' to '{path1}'")
        pardir, dest, name, _ = self.lookup(path1, False)
        if path_not_exist(pardir, dest, path1):
            return
        pardir, desc, name, _ = self.lookup(path2)
        if path_exist(pardir, desc, path2):
            return
        if len(list(pardir.links.keys())) > DESC_NUMBER:
            log_fail(f"Maximum file quantity reached!")
            return
        self.fs.link(Optional_unwrap(pardir), name, Optional_unwrap(dest))

    def unlink(self, path: str) -> None:
        log_info(f"Unlink link '{path}'")
        pardir, desc, name, _ = self.lookup(path, False)
        if path_not_exist(pardir, desc, path):
            return
        opened = 0
        if path in self.fd:
            opened = 1
        self.fs.unlink(Optional_unwrap(pardir), name, opened)

    def ls(self, path: str = "") -> None:
        log_info(f"List for '{path}'")
        desc: Optional[FileDesc]
        if path == "":
            desc = self.cwd
        else:
            pardir, desc, _, index = self.lookup(path)
            if path_not_exist(pardir, desc, path):
                return
            desc = Optional_unwrap(desc)
            pardir = None
        if desc_is_FileDir(desc, path):
            self.fs.ls(desc, self.cwd)

    def fstat(self, path: str) -> None:
        log_info(f"File stat for '{path}'")
        pardir, desc, _, index = self.lookup(path, False)
        if path_not_exist(pardir, desc, path):
            return
        print(f"id={index}", f"type={desc.type}", f"nlink={desc.nlink}", f"size={desc.size}", f"nblock={desc.nblock}")

    def pwd(self) -> None:
        log_info("Get CWD canonical absolute path")
        cwd_path = ""
        path = ""
        while True:
            _, desc1, _, _ = os.lookup(path + NAME_DOT)
            path = NAME_DOT_DOT + "/" + path
            _, desc2, _, _ = os.lookup(path)
            if desc1 == None or desc2 == None:
                log_fail("CWD was removed");
                return
            assert isinstance(desc1, FileDir)
            assert isinstance(desc2, FileDir)
            name = os.fs.reverse_lookup(Optional_unwrap(desc2),
                Optional_unwrap(desc1))
            if name == None:
                log_fail("CWD was removed")
                return
            if desc1 == desc2:
                if cwd_path == "":
                    cwd_path = "/"
                break
            cwd_path = "/" + Optional_unwrap(name) + cwd_path
        log_info(f"CWD canonical absolute path '{cwd_path}'")

    def truncate(self, path: str, size: int) -> None:
        log_info(f"Truncate file {path} size to {size}")
        pardir, desc, _, _ = self.lookup(path, False)
        if path_not_exist(pardir, desc, path):
            return
        size = math.ceil(int(size)/BLOCK_SIZE)*BLOCK_SIZE
        if size > desc.size:
            offset = desc.size
            text = "0"*(size - desc.size)
            text_arr, _ = self.split_text_to_write(desc, offset, text)
            for i in range(len(text_arr)):
                text_chunk = text_arr[i]
                success = self.fs.write(text_chunk, desc, offset)
                if success:
                    offset += len(text_chunk)
        elif size < desc.size:
            self.fs.free_blocks(desc, size)

    def open(self, path: str) -> int:
        log_info(f"Open file {path}")
        pardir, desc, _, _ = self.lookup(path, False)
        if path_not_exist(pardir, desc, path):
            self.create(path)
            pardir, desc, _, _ = self.lookup(path, False)
        if desc_is_FileDir(desc, path):
            log_fail(f"File '{path}' is a directory")
            return -1

        if len(path) > MAX_R:
            log_fail(f"Name '{path}' maximum length is {MAX_R}")
            return -1

        if len(list(pardir.links.keys())) > DESC_NUMBER:
            log_fail(f"Maximum file quantity reached!")
            return

        index = -1
        if None in self.fd:
            index = self.fd.index(None)
        else: 
            index = len(self.fd)
            self.fd.append(None)
            self.offsets.append(None)
        self.fd[index] = path
        self.offsets[index] = 0

        if index == -1:
            log_fail(f"Could not open file '{path}'")
        else:
            print(f"fd={index}")
        return index

    def fd_is_busy(self, fd: int) -> bool:
        if len(self.fd) < fd + 1 or \
         self.fd[fd] is None:
            return False
        return True

    def mkfs(self, n: int) -> None:
        self.fs.mkfs(n)
        self.cwd: FileDir = self.fs.rootdir
    
    def fs_initialized(self) -> bool:
        return self.fs.initialized

    def mount(self, fs: str) -> None:
        self.fs.mount(fs)
        self.cwd: FileDir = self.fs.rootdir

    def close(self, fd: int) -> None:
        fd = int(fd)
        if not self.fd_is_busy(fd):
            log_fail(f"Could not find opened fd='{fd}'")
            return
        path = self.fd[fd]
        pardir, desc, _, _ = self.lookup(path, False)
        if path_not_exist(pardir, desc, path):
            log_fail('Error! Path does not exist')
            return
        if desc.to_delete == 1:
            self.fs.unlink(Optional_unwrap(self.cwd), path, 0)
        self.fd[fd] = None
        self.offsets[fd] = None
        print("Closed!")
        return

    def read(self, fd: int, size: int) -> None:
        fd = int(fd)
        size = int(size)
        if not self.fd_is_busy(fd):
            log_fail(f"Could not find opened fd='{fd}'")
            return
        path = self.fd[fd]
        offset = self.offsets[fd]
        _, desc, _, _ = self.lookup(path, False)
        text = self.fs.read(size, desc, offset)
        self.offsets[fd] += size
        print(text)

    def seek(self, fd: int, offset: int) -> None:
        fd = int(fd)
        offset = int(offset)
        if not self.fd_is_busy(fd):
            log_fail(f"Could not find opened fd='{fd}'")
            return
        path = self.fd[fd]
        _, desc, _, _ = self.lookup(path, False)
        if int(desc.size) < offset:
            log_fail(f"Cannot seek to not existing position, file size='{desc.size}'")
            return
        self.offsets[fd] = offset
        log_info(f"Seek value set {offset}")
    
    def split_text_to_write(self, desc: FileReg, offset: int, text: str):
        first_chunk_size = self.fs.get_block_characters(desc, offset)
        text_arr = list()
        text_arr.append(text[0:first_chunk_size])
        text = text[first_chunk_size:]
        arr = [text[i:i+BLOCK_SIZE] for i in range(0, len(text), BLOCK_SIZE)]
        text_arr = text_arr + arr
        last_element_len = len(text_arr[-1])
        if last_element_len != BLOCK_SIZE:
            text_arr[-1] = text_arr[-1] + " " * (BLOCK_SIZE - last_element_len)
        return text_arr, last_element_len

    def write(self, fd: int, size: int) -> None:
        fd = int(fd)
        size = int(size)
        if not self.fd_is_busy(fd):
            log_fail(f"Could not find opened fd='{fd}'")
            return
        path = self.fd[fd]
        offset = self.offsets[fd]
        _, desc, _, _ = self.lookup(path, False)
        if desc_is_FileDir(desc, path):
            log_fail(f"Cannot write to directory")
            return 
        text = input("Insert data: ")
        if len(text) > size:
            text = text[0:size]
        text_arr, last_element_len = self.split_text_to_write(desc, offset, text)
        for i in range(len(text_arr)):
            text_chunk = text_arr[i]
            success = self.fs.write(text_chunk, desc, offset)
            if success:
                if i == len(text_arr) - 1:
                    self.offsets[fd] += last_element_len
                    offset += last_element_len  
                else: 
                    self.offsets[fd] += len(text_chunk)
                    offset += len(text_chunk)
        return


class Shell(cmd.Cmd):
    intro = 'Welcome!  Type help or ? to list commands.\n'
    prompt = '(manipulate fs) '
    file = None
    os = OS()

    def do_mkfs(self, arg):
        'Make FileSystem with arg as number of descriptors'
        self.os.mkfs(arg)

    def do_mount(self, arg):
        'Mount FileSystem with arg as name of the file, containing the filesystem'
        self.os.mount(arg)

    def do_ls(self, arg):
        'List files in current directory'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        self.os.ls(arg)

    def do_symlink(self, arg):
        'Create symbolic link: arg2 links to arg1'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.symlink(args[0], args[1])

    def do_link(self, arg):
        'Create hard link: arg2 links to arg1'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.link(args[0], args[1])

    def do_pwd(self, arg):
        'Print working directory'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        self.os.pwd()

    def do_create(self, arg):
        'Create new file'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        self.os.create(arg)

    def do_unlink(self, arg):
        'Destroy hard link'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        self.os.unlink(arg)

    def do_stat(self, arg):
        'Provide information on file'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        self.os.fstat(arg)

    def do_truncate(self, arg):
        'Change file size'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.truncate(args[0], args[1])

    def do_open(self, arg):
        'Open file'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.open(args[0])

    def do_close(self, arg):
        'Close file'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.close(args[0])

    def do_write(self, arg):
        'Write to file'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.write(args[0], args[1])

    def do_read(self, arg):
        'Read the file'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.read(args[0], args[1])

    def do_seek(self, arg):
        'Seek the specific position'
        if not self.os.fs_initialized():
            return log_fail('No filesystem initialized!')
        args = parse(arg)
        self.os.seek(args[0], args[1])

    def do_bye(self, arg):
        'Stop recording, close the window, and exit:  BYE'
        print('Bye!')
        self.close()
        return True

    def close(self):
        if self.file:
            self.file.close()
            self.file = None

def parse(arg):
    'Convert a series of zero or more numbers to an argument tuple'
    return tuple(map(str, arg.split()))

if __name__ == '__main__':
    Shell().cmdloop()
