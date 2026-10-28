import requests
import sys
import json 
from datetime import datetime


#this functio is responsible for loading cached data, return cached dat, read and return cached data
#should load the entire cache 
def load_cache_data():
    try:
        with open("cached.json") as cached_data:
            data = json.load(cached_data)
            return data #dict of dicts 

    except FileNotFoundError:
        return {} 
    
#check the freshness of data
#set a boundary 
def is_fresh(cached_data:dict,ttl=400) -> bool:
    #get the old cached time 
    time = cached_data["validated_at"] 

    #read string convert backinto datetime obj
    #desearlize timestamps back into datetime object 
    old_time = datetime.fromisoformat(time)
    current_time = datetime.now()

    #cal elpased time diff
    cache_age = (current_time - old_time).total_seconds()

    #if cache age <  TTL --> fresh
    #if cache age > TTL --> stale  

    if cache_age > ttl:
        return False #perform revalidation 
    
    return True #return cached data, the cached data will be new for another 400s 

#send conditonal request to github for revalidation 
def conditional_req(username:str, etag)-> dict:
    #revalidation header 
    headers = {"if-none-match": etag,
               "Accept": "application/vnd.github+json",
               "X-Github-Api-Version": "2026-03-10"}

    response  = requests.get(url=f"https://api.github.com/users/{username}/events",headers=headers,timeout=5)
    response.raise_for_status() #raise HTTP error

    #conditonal for response codes ?
    #no change
    result = {}
    if response.status_code == 304:
        result["status_code"] = response.status_code
        
    #there is change 
    elif response.status_code == 200:
        #return the new data ?
        data = response.json()
        #new representation of data     
        etag = response.headers.get("Etag")
        #put it inside dict 
        result["status_code"] = response.status_code
        result["data"] = data
        result["etag"] = etag
    
    return result 



#save data  from API requests 
def save_cache(to_be_cached):
    #write change into JSON, set to write mode 
    with open("cached.json","w") as save:
        json.dump(to_be_cached,save,indent=4)


#send normal API requests
def get_user_activity(username:str) -> tuple:

    headers = {"Accept": "application/vnd.github+json",
               "X-Github-Api-Version": "2026-03-10"}
    #send api requests
    response = requests.get(f"https://api.github.com/users/{username}/events",headers=headers,timeout=5)
    response.raise_for_status() #manage http behavior 

    dt = response.json() #a list of dicts 
    #need to save the etag 
    etag = response.headers.get("Etag")

    return dt,etag #returning a tuple 


#The data being loaded is from the JSON itself, through the load_cache data function, which will result in
#something like this a dict --> {"cached_at": cached_time,"validated_at": validated_time,"etag":etag,"events": to_be_cached}, the fucntio it taking this 
def format_data(data) -> list:
    push = 0 
    action_taken = []
    if data:
        #get the events of a specific user 
        events = data.get("events",[])  
        #iterate over the list of dicts 
        for event in events:
            #get the metadata val through the key 
            actor = event.get("actor",{}).get("login") #use the default for the last as by the time you are here youprobablay have access and no then it will just return None 
            event_type = event.get("type",{})
            repo_name = event.get("repo",{}).get("name")
            time_create = event.get("created_at",{})
            #the type of the event determines the specific payload, some events might share the same key 
            payload = event.get("payload",{}) #each event has its payload, specific details regarding what happended in this event type 

            #!this might be inefficient but we are targeting specific events in here so 
            if event_type == "PushEvent":
                branch = payload.get("ref","unknown ref")
                action_taken.append(f"{actor} pushed to {branch} in {repo_name} at {time_create}")
        
            elif event_type == "CreateEvent":
                ref_type = payload.get("ref_type")
                ref = payload.get("ref")
                action_taken.append(f"{actor} created {ref_type} {ref or repo_name} at {time_create}")
        
            elif event_type == "DeleteEvent":
                action_taken.append(f"{actor} deleted branch {repo_name} at {time_create}")
        
            elif event_type == "ForkEvent":
                action_taken.append(f"{actor} {payload.get('action')} repository {repo_name} at {time_create}")
            
            elif event_type == "IssuesEvent":
                action_taken.append(f"{actor} {payload.get('action')} issue in {repo_name} at {time_create}")
            
            elif event_type == "PullRequestEvent":
                action_taken.append(f"{actor} {payload.get('action')} pull request on {repo_name} at {time_create}")
            
            elif event_type == "WatchEvent":
                action_taken.append(f"{actor} {payload.get('action')} repository {repo_name} at {time_create}")
            
            elif event_type == "ReleaseEvent":
                action_taken.append(f"{actor} {payload.get('action')} release on {repo_name} at {time_create}")
            
            else:
                action_taken.append(f"{actor} triggered a {event_type} event on {repo_name} at {time_create}") #!for all the other unknown events 

        return action_taken

    else:
        return [] #!if there is no recent activity in the repo, return [] which denotes to None 
    

def main():
    #check arguments from command line 
    n_args = len(sys.argv)
    if n_args != 2: #script name and name argument 
        sys.exit(f"Invalid amount of arguments -> {sys.argv}, expected 1 argument, not {n_args}")

    try:
        #load cache first , file not found expected
        #this is the entire cache consisting caches foe different users
        cache = load_cache_data() #dict of dicts 
        #get username
        username = sys.argv[1] #str
        #user specific cache  
        user_cache = cache.get(username) # dicts            
        
        if user_cache is None:
            #make fresh reqests 
            usr_data, Etag = get_user_activity(sys.argv[1])

            now = datetime.now().isoformat()
                  #perform saving, load the data into the file
            #build cache here
            #instead of putting inside the  save function so the save function literally performs save 

            cache[username] = {
                "cached_at":now,
                "validated_at": now,
                "etag":Etag,
                "events":usr_data #still a list of dicts 
            }

            #save the user data into the cache 
            save_cache(cache)
            #load data and format 
            for fmt in format_data(cache[username]):
                print(fmt)
        else:
            #there is cache and not fresh
            if not is_fresh(user_cache):
                #old etag
                etag = user_cache["etag"]
                #perform revalidation
                result = conditional_req(sys.argv[1],etag)

                #signifying the state of the resource 
                if result["status_code"] == 304:
                    print("Github verified that the data has not changed")
                    #update validated timestamp
                    user_cache["validated_at"] = datetime.now().isoformat()
                    #NEED TO SAVE THE CHANGE, timestamp change , save the updated check time 
                    save_cache(cache)
                    #load prvious cache
                    for fmt in format_data(user_cache):
                        print(fmt)

                elif result["status_code"] == 200: 
                    print("Changes made to data")
                    #get the new data and etag (data rep)
                    data = result["data"]
                    e_tag = result["etag"]
                    #make the change 
                    user_cache["validated_at"] = datetime.now().isoformat()
                    user_cache["cached_at"] = datetime.now().isoformat()
                    user_cache["etag"] = e_tag
                    user_cache["events"] = data
                    #SAVE the changes 
                    save_cache(cache)
                    #load updated cache 
                    for fmt in format_data(user_cache):
                        print(fmt)
            else:
                #cache still fresh 
                for fmt in format_data(user_cache):
                    print(fmt)


    except requests.ConnectionError as cnt:
        print(f"Unable to establlish connection: {cnt}")
        return 
    except requests.HTTPError as htp:
        print(f"{htp}")
        return 

    except requests.Timeout as t:
        print(f"Server took too long to respond:{t}")

    except json.JSONDecodeError as js:
        print(f"{js}")

    except requests.RequestException as err: #this catches the raised specific error related to API 
        print(f"Something went wrong: {err}")
        return 

if __name__ == "__main__":
    main()
