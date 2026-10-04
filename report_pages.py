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

def page(view,source,index,language='en'):
    labels={'en':('Details','Listing','Rates & assumptions','Page'),
            'de':('Details','Anzeige','Zinsen & Annahmen','Seite'),
            'fa':('جزئیات','آگهی','نرخ بهره و فرض‌ها','صفحه')}
    detail,listing,notes,page_label=labels.get(language,labels['en'])
    total=(len(view['cards'])+PAGE_SIZE-1)//PAGE_SIZE
    if not 0<=index<total: raise ValueError('Invalid report page')
    text=[view['header'],f'{page_label} {index+1}/{total}']
    buttons=[]
    for i in range(index*PAGE_SIZE,min((index+1)*PAGE_SIZE,len(view['cards']))):
        card=view['cards'][i]
        text.append(f'\n{i+1}. '+card['brief'].removeprefix('🏠 — '))
        buttons.append([{'text':f'{detail} {i+1}','callback_data':f'prop:{source}:{i}'},
                        {'text':'🔗 '+listing,'url':card['url']}])
    disclaimer=view['notes'].splitlines()[-1] if view['notes'] else ''
    if disclaimer: text.append('\n'+disclaimer)
    nav=[]
    if index: nav.append({'text':'◀️','callback_data':f'list:{source}:{index-1}'})
    if index+1<total: nav.append({'text':'▶️','callback_data':f'list:{source}:{index+1}'})
    if nav: buttons.append(nav)
    if view['notes']: buttons.append([{'text':'💶 '+notes,'callback_data':f'notes:{source}'}])
    return '\n'.join(text),{'inline_keyboard':buttons}
