import requests
from time import sleep
import re
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from tqdm import tqdm

class PlaylistConverter:

    def __init__(self, url, driver_location, token, playlist=None):
        self.token = token
        if playlist == None:
            rows = self.scrapeSongs(url, driver_location)
            self.playlist = self.generatePlaylist(rows)
        else:
            self.playlist = playlist
        self.matches = []

    def run2(self):
        uris = []
        skipped = []
        for entry in tqdm(self.playlist):
            entry_c = self.cleanEntry(entry)
            match = self.match_logic2(entry_c)
            if match != None:
                self.matches.append([entry, match])
                uri = match['uri']
                uris.append(uri)
            else:
                skipped.append(entry)
        
        return uris, skipped

    def run(self):
        uris = []
        skipped = []
        for entry in self.playlist:
            uri = self.matchingLogic(entry)
            if uri != None:
                uris.append(uri)
            else:
                skipped.append(entry)
        return uris, skipped

    @staticmethod
    def search(song='', artist='', album='', token='', search_type='track'):
        baseURL = "https://api.spotify.com/v1/search"

        # convert space to %20
        song = song.replace(" ", "%20").replace("&", "and")
        artist = artist.replace(" ", "%20").replace("&", "and")
        album = album.replace(" ", "%20").replace("&", "and")

        query = 'q='
        if song != '':
            query += f"{song}"
        if artist != '':
            query += f"%20artist:{artist}"
        if album != '':
            query += f"%20album:{album}"
        
        query += f"&type={search_type}"

        response = requests.get(url=f"{baseURL}?{query}", headers={"Content-Type":"application/json", 
                        "Authorization":f"Bearer {token}"})

        j = response.json()

        if int(response.status_code) == 429: # too many requests
            # we must wait
            print(f"Rate limiting! Sleeping for {j['Retry-After']}")
            sleep(int(j['Retry-After']) + 1)
            response = requests.get(url=f"{baseURL}?{query}", headers={"Content-Type":"application/json", 
                            "Authorization":f"Bearer {token}"})
        elif int(response.status_code) != 200:
            print(f"Error code: {response.status_code}")
            raise Exception(response.status_code)

        return j
    
    @staticmethod
    def spotify_search_to_playlist(search_response):
        '''
        Makes the search response use the same structure as the self.playlist dictionary
        for ease
        '''
        playlist = []
        for item in search_response['tracks']['items']:
            entry = {}
            entry['song'] = item['name']
            entry['artist'] = [artist['name'] for artist in item['artists']]
            entry['album'] = item['album']['name']
            entry['uri'] = item['uri']
            playlist.append(entry)
        
        return playlist
    
    def bag_matching(self, entry: dict, search_playlist: list):
        '''
        For each entry returned from search, get the cosine similarity
        Save the uri for the best one
        '''
        entry_bag = " ".join([entry['song'], entry['album']] + entry['artist']).split(' ')
        entry_bag_l = [e.lower() for e in entry_bag]
        search_bags = [' '.join([se['song'], se['album']] + se['artist']).split(' ') for se in search_playlist]
        highest_similarity = 0
        matched_entry = None
        for i, search_bag in enumerate(search_bags):
            search_bag_l = [e.lower() for e in search_bag]
            similarity = self.get_cosine_similarity(entry_bag_l, search_bag_l)
            if similarity > highest_similarity:
                highest_similarity = similarity
                matched_entry = search_playlist[i]
        
        return matched_entry

    @staticmethod 
    def get_cosine_similarity(entry1, entry2):
        # form a set containing keywords of both strings 
        # print(f"cf {entry1} : {entry2}")
        l1 = []
        l2 = []
        rvector = set(entry1) #.union(set(entry2)) 
        for w in rvector:
            if w in entry1: l1.append(1) # create a vector
            else: l1.append(0)
            if w in entry2: l2.append(1)
            else: l2.append(0)

        c = 0
        
        # cosine formula 
        for i in range(len(rvector)):
                c+= l1[i]*l2[i]
        try:
            cosine = c / float((sum(l1) * sum(l2))**0.5)
        except ZeroDivisionError:
            cosine = 0

        return cosine

    def match2(self, entry, search_entry):
        '''
        Search with search_entry (search entry might be modified for a better search)
        Match to real entry
        '''
        artists_str = ",".join(search_entry['artist'])
        resp = self.search(song=search_entry['song'], artist=artists_str, album=search_entry['album'], token=self.token)

        if len(resp['tracks']['items']) <= 0:
            return None

        search_playlist = self.spotify_search_to_playlist(resp)
        match = self.bag_matching(entry, search_playlist)
        return match

    def match_logic2(self, entry):
        '''modify entries to return a search'''
        entry_mod = entry.copy()

        entry_mod['album'] = ''

        # default
        r = self.match2(entry, entry_mod)
        if r != None:
            return r
        
        # replace & with ,
        print(f"Searching for {entry} without &...")
        entry_mod['artist'] = [e.replace("&", ",") for e in entry_mod['artist']]
        r = self.match2(entry, entry_mod)
        if r != None:
            return r
        
        # remove weird symbols
        print(f"Searching for {entry} without symbols...")
        entry_mod['artist'] = [re.sub('[^0-9a-zA-Z ]+', '', e) for e in entry_mod['artist']]
        r = self.match2(entry, entry_mod)
        if r != None:
            return r

        # use song name only
        print(f"Searching for {entry} with just song name...")
        entry_mod['album'] = ''
        r = self.match2(entry, entry_mod)
        if r != None:
            return r
        '''
        # use album and song name
        print(f"Searching for {entry} without artist & with album...")
        entry['album'] = album
        entry['artist'] = []
        r = self.match2(entry)
        if r != None:
            return r

        '''

    
    @staticmethod
    def matchTrackSearch(search_response, song_apple='', artists_apple=[], album_apple='', auto_match=True, token=''):
        '''
        Take a bunch of tracks from a spotify query and try to match it 
        '''
        # lowercase for ease of match
        song_apple = song_apple.lower()
        artists_apple = [artist.lower() for artist in artists_apple]
        album_apple = album_apple.lower()

        uri = None
        for item in search_response['tracks']['items']:
            song_spotify = item['name'].lower()
            artists_spotify = [artist['name'].lower() for artist in item['artists']]
            album_spotify = item['album']['name'].lower()

            # print(f"Item: {song_spotify} by {artists_spotify} on album_spotify")
            if auto_match:
                # auto match if no conditionals are given
                match = True 

            # create conditional
            if song_apple != '':
                match = song_spotify == song_apple
            if len(artists_apple) != 0:
                # check that every apple artist is in the spotify artists
                for artist_a in artists_apple:
                    print(f"{artist_a} -> {artists_spotify}")
                    match = match and artist_a in artists_spotify
            if album_apple != '':
                match = match and album_spotify == album_apple
            
            if match:
                msg = "Match found!\n"
                if song_apple != '':
                    msg += f"\t{song_spotify} == {song_apple}\n"
                if artists_apple != '':
                    msg += f"\t{artists_spotify} == {artists_apple}\n"
                if album_apple != '':
                    msg += f"\t{album_spotify} == {album_apple}\n"

                print(msg)
                uri = item['uri']
                break

        return uri

    def matchingLogic(self, entry):
        '''
        1. Search by song and artist
        2. Search by song and artist after cleaning the entry
        3. search by song and first artist first name
        '''
        entry = self.addArtists(entry)

        uri = self.match(entry['song'], entry['artist'], entry['album'])
        if uri != None:
            return uri

        # clean song name, artists, etc 
        entry = self.cleanEntry(entry)

        uri = self.match(entry['song'], entry['artist'], entry['album'])
        if uri != None:
            return uri

        artists_fname = [artist.split(" ") for artist in entry['artist']]
        print(f"Firstname = {artists_fname}")
        uri = self.match(entry['song'], artists_fname, entry['album'])
        if uri != None:
            return uri
        
        print(f"Failed to find URI for {entry['song']} by {entry['artist']} on {entry['album']}")
        return None

    def match(self, song, artists, album):
        '''
        1. Try to match song and multiple artists 
        2. Try to match song with one artist
        '''
        # first search by song and artist
        for artist in artists:
            resp = self.search(song=song, artist=artist, token=self.token)

            if len(resp['tracks']['items']) > 0:
                uri = self.matchTrackSearch(resp, song_apple=song, artists_apple=artists, auto_match=False, token=self.token)

                if uri != None:
                    return uri

                # match one artist
                for artist in artists:
                    uri = self.matchTrackSearch(resp, song_apple=song, artists_apple=[artist], auto_match=False, token=self.token)
                    if uri != None:
                        return uri

        return None

    def addArtists(self, entry):
        paren_pattern = r"\(([^)]+)"
        parens = re.findall(paren_pattern, entry['song'])

        pat = r"feat\.|with"
        if len(parens) != 0 and re.match(pat, parens[0]):
            artist = re.sub(pat, "", parens[0]).strip()
            song = re.sub(paren_pattern + "|\)", "", entry['song']).strip()
            entry['artist'].extend([artist])
            entry['song'] = song

        '''
        pat = "\(([^)]+)"
        between_parens = re.findall(pat, entry['song'])
        if len(result) != 0:
            # add artist and remove parentheses
            re.sub("\)|\(feat\.|\(with", "", entry['song'])
            artist = result[0].strip()
            entry['artist'].extend(artist)
            re.sub(r" ?\([^)]+\)", "", entry['song'])
        '''

        return entry

    def cleanEntry(self, entry):
        '''
        Remove anything between []
        Remove anything between ()
        '''
        paren_pattern = " ?\([^)]+\)"
        bracket_pattern = " ?\[[^)]+\]"
        for key in entry.keys():
            if key == 'artist':
                for i in range(len(entry[key])):
                    entry[key][i] = re.sub(paren_pattern, "", entry['artist'][i])
                    entry[key][i] = re.sub(bracket_pattern, "", entry['artist'][i])
            else:
                entry[key] = re.sub(paren_pattern, "", entry['song'])
                entry[key] = re.sub(bracket_pattern, "", entry['song'])

        return entry

    def scrapeSongs(self, url, exec_path):
        driver = webdriver.Chrome(executable_path=exec_path)
        driver.implicitly_wait(30)
        driver.get(url)

        ScrollNumber = 5
        for i in range(1,ScrollNumber):
            driver.execute_script("window.scrollTo(1,50000)")
            sleep(5)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.close()
        rows = soup.find_all("div", attrs="songs-list-row")
        return rows

    def generatePlaylist(self, rows):
        playlist = []
        for i, row in enumerate(rows):
            entry = {}
            entry["song"] = row.find("div", attrs="songs-list-row__song-name").string
            entry["artist"] = [row.find_all("a", attrs="songs-list-row__link")[0].string]
            entry["album"] = row.find_all("a", attrs="songs-list-row__link")[-1].string
            playlist.append(entry)
        
        return playlist
    

if __name__ == "__main__":
    pc = PlaylistConverter()
    pc.run()