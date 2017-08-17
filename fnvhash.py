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

if __name__ == "__main__":
    from itertools import combinations
    
    while True:
        _input = input("Enter the name: ")
        if _input != "exit!!":
            v = fnvhash(_input)
            print(hex(v), v)
        else:
            break
    
    """
    s = '\Events\Default Work Unit\MUS_Loading\MUS_Loading32'
    for l in range(1, len(s)+1):
        for i in range(len(s)):
            if i + l <= len(s):
                word = s[i:i+l]
            if fnvhash(word) == 863985236:
                print(word)
    """
