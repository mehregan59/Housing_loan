"""Compact Telegram index and stored details, without additional AI calls."""
import re
PAGE_SIZE=5

def split_report(report):
    headings=list(re.finditer(r'^((?:🏠 — |🔄[^\n]* — ).*)$',report,re.M))
    if not headings: return {'header':report,'cards':[],'notes':''}
    notes_start=report.find('\n💶 ',headings[-1].end())
    if notes_start<0: notes_start=len(report)
    cards=[]
    for i,h in enumerate(headings):
        end=headings[i+1].start() if i+1<len(headings) else notes_start
        block=report[h.start():end].strip()
        lines=block.splitlines()
        urls=re.findall(r'https?://\S+',lines[-1])
        if not urls: return {'header':report,'cards':[],'notes':''}
        brief=[lines[0]]
        for prefix in ('📍','🏷','📐','💵','🏦','💳','📈'):
            brief.extend(line for line in lines if line.startswith(prefix))
        cards.append({'detail':block,'brief':'\n'.join(brief),'url':urls[-1]})
    return {'header':report[:headings[0].start()].strip(),'cards':cards,'notes':report[notes_start:].strip()}

def bot_link(source,kind,index=None,username='MeHousingLoanBot'):
    payload=kind+'_'+source+('\u005f'+str(index) if index is not None else '')
    if len(payload)>64 or not re.fullmatch(r'[A-Za-z0-9_-]+',payload): raise ValueError('Invalid report link')
    if not re.fullmatch(r'[A-Za-z0-9_]+',username): raise ValueError('Invalid bot username')
    return 'https://t.me/'+username+'?start='+payload


def add_link(text,entities,label,target):
    entities.append({'type':'text_link','offset':len(text.encode('utf-16-le'))//2,
                     'length':len(label.encode('utf-16-le'))//2,'url':target})
    return text+label


def page(view,source,index,language='en',username='MeHousingLoanBot'):
    labels={'en':('Details','Listing','Rates & assumptions','Page'),
            'de':('Details','Anzeige','Zinsen & Annahmen','Seite'),
            'fa':('جزئیات','آگهی','نرخ بهره و فرض‌ها','صفحه')}
    detail,listing,notes,page_label=labels.get(language,labels['en'])
    total=(len(view['cards'])+PAGE_SIZE-1)//PAGE_SIZE
    if not 0<=index<total: raise ValueError('Invalid report page')
    text=view['header']+'\n'+f'{page_label} {index+1}/{total}'
    entities=[]
    for i in range(index*PAGE_SIZE,min((index+1)*PAGE_SIZE,len(view['cards']))):
        card=view['cards'][i]
        text+=f'\n\n{i+1}. '+card['brief'].removeprefix('🏠 — ')+' · '
        text=add_link(text,entities,detail,bot_link(source,'prop',i,username))+' · '
        text=add_link(text,entities,listing,card['url'])
    text+='\n\n'
    if index: text=add_link(text,entities,'◀️',bot_link(source,'list',index-1,username))+'  '
    if index+1<total: text=add_link(text,entities,'▶️',bot_link(source,'list',index+1,username))+'  '
    if view['notes']: text=add_link(text,entities,'💶 '+notes,bot_link(source,'notes',username=username))
    disclaimer=view['notes'].splitlines()[-1] if view['notes'] else ''
    if disclaimer: text+='\n\n'+disclaimer
    return text,entities
