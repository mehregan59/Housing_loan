"""Pinned, versioned private reminders. No OpenAI calls, no fabricated acknowledgements."""
import os
from datetime import datetime,timezone

GUIDE_VERSION=1

def required_notices(user,control):
    result=[]
    if user.get('service','investment')=='investment' and user.get('settings',{}).get('_guide_version')!=GUIDE_VERSION:
        lang=user.get('settings',{}).get('language','en')
        text={'en':'📌 Setup guide not completed\nPlease read the guide and finish the final step. This reminder stays pinned until you finish. Approved pilot weekly reports can still arrive. Manual searches require the guide.',
              'de':'📌 Einrichtungsanleitung noch nicht abgeschlossen\nBitte die Anleitung lesen und den letzten Schritt abschließen. Diese Erinnerung bleibt bis dahin angeheftet. Genehmigte Pilot-Wochenberichte können trotzdem ankommen. Manuelle Suchen erfordern die Anleitung.',
              'fa':'📌 راهنمای شروع هنوز تکمیل نشده است\nراهنما را بخوانید و مرحله پایانی را تکمیل کنید. این یادآوری تا پایان راهنما سنجاق می‌ماند. گزارش هفتگی کاربران آزمایشی تأییدشده همچنان ارسال می‌شود. جستجوی دستی به تکمیل راهنما نیاز دارد.'}.get(lang)
        result.append(('guide',GUIDE_VERSION,text or '📌 Please complete /guide. This reminder stays pinned until completion.','guide:resume'))
    version=control.get('agreement_version',1)
    if user.get('agreement_version_accepted',1 if user.get('accepted_at') else 0)<version and control.get('agreement_text'):
        result.append(('agreement',version,'📌 Updated user agreement — version '+str(version)+'\n\n'+control['agreement_text']+'\n\nPlease review and accept. This reminder stays pinned until acceptance.','agreement:'+str(version)))
    return result

def telegram(db,method,body):
    r=db.http.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/'+method,json=body)
    data=r.json()
    if not r.is_success or not data.get('ok'): raise RuntimeError('NoticeTelegramFailure')
    return data.get('result')

def reconcile_user(db,user,control):
    uid=user['user_id'];wanted={(kind,version):(text,action) for kind,version,text,action in required_notices(user,control)}
    rows=db.request('GET','bot_notices?user_id=eq.'+str(uid))
    for row in rows:
        if row.get('acknowledged_at') or (row['kind'],row['version']) in wanted: continue
        # Only remove this bot's own stored message, never all chat pins.
        if row.get('message_id') and row.get('pinned'): telegram(db,'unpinChatMessage',{'chat_id':uid,'message_id':row['message_id']})
        completed=(row['kind']=='guide' and user.get('settings',{}).get('_guide_version',0)>=row['version']) or (row['kind']=='agreement' and user.get('agreement_version_accepted',0)>=row['version'])
        db.request('PATCH',f"bot_notices?user_id=eq.{uid}&kind=eq.{row['kind']}&version=eq.{row['version']}",{'pinned':False,**({'acknowledged_at':datetime.now(timezone.utc).isoformat()} if completed else {})})
    for (kind,version),(text,action) in wanted.items():
        path=f'bot_notices?user_id=eq.{uid}&kind=eq.{kind}&version=eq.{version}'
        row=next((x for x in rows if x['kind']==kind and x['version']==version),None)
        if row is None:
            db.request('POST','bot_notices',{'user_id':uid,'kind':kind,'version':version})
            row={'message_id':None,'pinned':False}
        if row.get('acknowledged_at'): continue
        if not row.get('message_id'):
            sent=telegram(db,'sendMessage',{'chat_id':uid,'text':text[:3800],'reply_markup':{'inline_keyboard':[[{'text':'📖 Open guide' if kind=='guide' else 'I have read and accept v'+str(version),'callback_data':action}]]},'link_preview_options':{'is_disabled':True}})
            message_id=(sent or {}).get('message_id')
            if not isinstance(message_id,int): raise RuntimeError('NoticeMessageIdMissing')
            row['message_id']=message_id
            db.request('PATCH',path,{'message_id':message_id})
        # Recheck completion before pinning; a webhook may finish the guide while sending.
        current=db.request('GET','bot_users?user_id=eq.'+str(uid))
        if not current or (kind,version) not in {(k,v) for k,v,_,_ in required_notices(current[0],control)}:
            continue
        telegram(db,'pinChatMessage',{'chat_id':uid,'message_id':row['message_id'],'disable_notification':True})
        if not row.get('pinned'): db.request('PATCH',path,{'pinned':True})

def sweep_notices(db,control):
    if not control.get('notices_enabled'): return
    for user in db.request('GET','bot_users?approved=eq.true&accepted_at=not.is.null'):
        try: reconcile_user(db,user,control)
        except Exception:
            # A reminder failure must never block the scheduled reports.
            pass
