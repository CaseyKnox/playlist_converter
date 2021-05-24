import requests
from time import sleep
import re
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from tqdm import tqdm
import copy
import json

class PlaylistConverter:

    def __init__(self, url, driver_location, token, playlist=None):
        self.token = token
        if playlist == None:
            rows = self.scrapeSongs(url, driver_location)
            self.playlist = self.generatePlaylist(rows)
        else:
            self.playlist = playlist
        self.matches = []

    def run(self):
        uris = []
        skipped = []
        for entry in tqdm(self.playlist):
            # entry_c = self.cleanEntry(entry.copy())
            entry_c = copy.deepcopy(entry)
            match = self.match_logic(entry_c)
            if match != None:
                self.matches.append([entry, match])
                uri = match['uri']
                uris.append(uri)
            else:
                skipped.append(entry)
        
        return uris, skipped

    @staticmethod
    def search(song='', artist='', album='', token='', search_type='track'):
        baseURL = "https://api.spotify.com/v1/search"

        # convert space to %20
        song = song.replace(" ", "%20").replace("&", "")
        artist = artist.replace(" ", "%20").replace("&", "")
        album = album.replace(" ", "%20").replace("&", "")

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
    
    def spotify_search_to_playlist(self, search_response):
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
                matched_entry['similarity'] = similarity
        
        return matched_entry

    @staticmethod 
    def get_cosine_similarity(entry1, entry2):
        # form a set containing keywords of both strings 
        # print(f"cf {entry1} : {entry2}")
        l1 = []
        l2 = []
        rvector = set(entry1).union(set(entry2)) 
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

    def match(self, entry, search_entry):
        '''
        Search with search_entry (search entry might be modified for a better search)
        Match to real entry
        '''
        artists_str = " ".join(search_entry['artist'])
        resp = self.search(song=search_entry['song'], artist=artists_str, album=search_entry['album'], token=self.token)

        if len(resp['tracks']['items']) <= 0:
            return None

        search_playlist = self.spotify_search_to_playlist(resp)
        search_playlist = [self.cleanEntry(e) for e in search_playlist]
        # search_playlist['artist'] = [re.sub('\(\)\[\]', '', e) for e in search_playlist['artist']]
        match = self.bag_matching(entry, search_playlist)
        return match

    def match_logic(self, entry):
        '''modify entries to return a search'''
        entry_mod = copy.deepcopy(entry)
        entry_mod['album'] = ""
        matches = []

        entry_mod = self.addArtists(entry_mod)
        # print(entry_mod)
        # default
        r = self.match(entry, entry_mod)
        if r != None:
            matches.append(r)
        
        # clean
        entry_mod = self.cleanEntry(entry_mod)
        # print("[Clean] " + str(entry_mod))
        r = self.match(entry, entry_mod)
        if r != None:
            matches.append(r)

        # replace & with ,
        # print(f"Searching for {entry} without &...")
        entry_mod['artist'] = [e.replace("&", ", ") for e in entry_mod['artist']]
        # print("[rm &] " + str(entry_mod))
        r = self.match(entry, entry_mod)
        if r != None:
            matches.append(r)
        
        # remove weird symbols
        # print(f"Searching for {entry} with only alphanumerics...")
        entry_mod['artist'] = [re.sub('[^0-9a-zA-Z ]+', '', e) for e in entry_mod['artist']]
        # print("[alp-num] " + str(entry_mod))
        r = self.match(entry, entry_mod)
        if r != None:
            matches.append(r)

        best_sim = 0
        best_match = None
        for m in matches:
            if m['similarity'] > best_sim:
                best_sim = m['similarity']
                best_match = m

        return best_match

        '''
        # use album and song name
        print(f"Searching for {entry} without artist & with album...")
        entry['album'] = album
        entry['artist'] = []
        r = self.match(entry)
        if r != None:
            return r

        # use song name only
        print(f"Searching for {entry} with just song name...")
        entry_mod['album'] = ''
        r = self.match(entry, entry_mod)
        if r != None:
            return r
        '''

    @staticmethod
    def addArtists(entry_og):
        entry = copy.deepcopy(entry_og)
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

    def cleanEntry(self, entry_og):
        '''
        Remove anything between []
        Remove anything between ()
        '''
        entry = copy.deepcopy(entry_og)
        paren_pattern = " ?\([^)]+\)"
        bracket_pattern = " ?\[[^)]+\]"
        for key in entry.keys():
            if key == 'artist':
                for i in range(len(entry[key])):
                    entry[key][i] = re.sub(paren_pattern, "", entry[key][i])
                    entry[key][i] = re.sub(bracket_pattern, "", entry[key][i])
            else:
                entry[key] = re.sub(paren_pattern, "", entry[key])
                entry[key] = re.sub(bracket_pattern, "", entry[key])

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
    
    @staticmethod
    def create_playlist(uid, playlist_name, desc='', public=False, token=''):
        endpoint_url = f"https://api.spotify.com/v1/users/{uid}/playlists"
        request_body = json.dumps({
                "name": playlist_name,
                "description": desc,
                "public": public
                })
        response = requests.post(url = endpoint_url, data = request_body, headers={"Content-Type":"application/json", 
                                "Authorization":f"Bearer {token}"})
        j = response.json()

        if int(response.status_code) != 201:
            print(f"Error code: {response.status_code}")
            print(f"{response}")
            raise Exception(response.status_code)

        return j

    @staticmethod
    def upload_to_spotify(playlist_id, uris, token=''):
        endpoint_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"

        # upload in batches of 100
        for i in range(0, len(uris), 100):
            request_body = json.dumps({
                    "uris" : uris[i:i+100]
                    })
            response = requests.post(url=endpoint_url, data=request_body, headers={"Content-Type":"application/json", 
                                    "Authorization":f"Bearer {token}"})
            j = response.json()

            if int(response.status_code) != 201:
                print(f"Error code: {response.status_code}")
                print(f"{response}")
                raise Exception(response.status_code)

    def printAssumedMatches(self):
        '''
        Print the matches where the song titles do not match exactly
        '''
        for m in self.matches:
            if m[0]['song'].lower() != m[1]['song'].lower():
                # 0 is requested, 1 is the found match
                print(f"Requested              ------------------->            Assumed Match")
                print(f"{m[0]['song']} by {m[0]['artist']} --> {m[1]['song']} by {m[1]['artist']}")

    

if __name__ == "__main__":
    pc = PlaylistConverter()
    pc.run()