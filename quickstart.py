from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import datetime as dt

DONE_COLOR = '8' # apparently, this is my color ID for gray

def term_cols():
    import os
    _, cols = os.popen('stty size', 'r').read().split()
    return int(cols)

# timedelta -> str, str
def dayspan(day_delta=0):
    from dateutil import tz
    today = (dt.datetime.now()).date() + dt.timedelta(days=day_delta)
    start = dt.datetime(
        today.year, today.month, today.day,
        tzinfo = tz.gettz('America/New_York'))
    end = start + dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()

# -> service
def get_service():
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/calendar.events'] # rw access to events
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build('calendar', 'v3', credentials=creds)

# service, mut event -> Request
def mk_allday(service, event):
    def collapse(timepoint):
        if 'date' in timepoint:
            return timepoint
        dt = timepoint['dateTime']
        return {'date': dt[:dt.index('T')]}
    event['start'] = collapse(event['start'])
    event['end'] = collapse(event['end'])
    return service.events().update(calendarId='primary', eventId=event['id'], body=event)

def isallday(event):
    return (
        'start' in event and 
        'end' in event and
        'date' in event['start'] and
        'date' in event['end'])

def isdone(event): return event.get('colorId', None) == DONE_COLOR
def neg(f): return lambda x: not f(x)

# type state = [event], [event]

def pp(state):
    done, pending = state
    for event in done:
        print(event['summary'])
    print('-' * term_cols())
    for event in pending:
        print(event['summary'])
    return done, pending

# service, int -> state
def ls(service, day_delta=0):
    day_l, day_r = dayspan(day_delta=day_delta)
    events = list(filter(isallday, service
        .events()
        .list(
            calendarId='primary',
            timeMin=day_l, timeMax=day_r,
            maxResults=50, singleEvents=True,
            orderBy='startTime')
        .execute()
        .get('items', [])))
    sort = lambda xs: sorted(xs, key=lambda e: e.get('summary', ''))
    return sort(filter(isdone, events)), sort(filter(neg(isdone), events))

# service, str, state -> None
def mark(service, name, state):
    _, pending = state
    for e in filter(lambda e: name in e['summary'], pending):
        e['colorId'] = DONE_COLOR
        service.events().update(calendarId='primary', eventId=e['id'], body=e).execute()
        break

# service, str, state -> None
def unmark(service, name, state):
    done, _ = state
    for e in filter(lambda e: name in e['summary'], done):
        if 'colorId' in e:
            del e['colorId']
        service.events().update(calendarId='primary', eventId=e['id'], body=e).execute()
        break

# service, str, state -> None
def remove(service, name, state):
    done, pending = state
    for e in filter(lambda e: name in e['summary'], done + pending):
        if input('Delete ' + e['summary'] + '? (y/any) ') == 'y':
            service.events().delete(calendarId='primary', eventId=e['id']).execute()
        break

# service, str, day_delta=int -> None
def make(service, name, day_delta=0):
    day_l, _ = dayspan(day_delta=day_delta)
    day = day_l[:day_l.index('T')]
    service.events().insert(calendarId='primary', body={
        'summary': name,
        'start': {'date': day},
        'end': {"date": day},
    }).execute()

if __name__ == '__main__':
    service = get_service()
    delta = 0
    while True:
        toks = input('> ').split()
        if not toks:
            continue
        cmd, *args = toks
        if cmd == 'a':
            delta -= 1
        elif cmd == 'r':
            delta += 1
        elif cmd == 'p':
            print(f'delta = {delta}')
        elif cmd == 'l':
            pp(ls(service, day_delta=delta))
        elif cmd == 'ok':
            if len(args) == 1:
                mark(service, args[0], ls(service, day_delta=delta))
            else:
                print('ok <substring of event name to mark as done>')
        elif cmd == 're':
            if len(args) == 1:
                unmark(service, args[0], ls(service, day_delta=delta))
            else:
                print('re <substring of event name to reopen>')
        elif cmd == 'rm':
            if len(args) == 1:
                remove(service, args[0], ls(service, day_delta=delta))
            else:
                print('rm <substring of event name to remove>')
        elif cmd == 'mk':
            if args:
                make(service, ' '.join(args), day_delta=delta)
            else:
                print('mk <name of event to add>')
        else:
            print('Valid commands: a, r, p, l, ok, re, rm, mk')
