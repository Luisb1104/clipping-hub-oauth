from PIL import Image, ImageDraw, ImageFont
import os
D=os.path.dirname(os.path.abspath(__file__))
F=lambda b,s: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf'%('-Bold' if b else ''),s)
L=lambda t,n: Image.open(f'{D}/clip-sky1-{t}-{n}.png')
def rs(im,w): return im.resize((w,int(im.height*w/im.width)),Image.LANCZOS)
PH=[('phone-overview','Overview'),('phone-queue','Queue'),('phone-earnings','Earnings'),('phone-flags','Flags'),('phone-costs','Costs'),('phone-connect','Connect'),('phone-queue-empty','Queue · empty'),('phone-flags-empty','Flags · empty'),('phone-earnings-empty','Earnings · empty')]
def contact(t):
    bg='#0b0d16' if t=='dark' else '#eef1fb'; fg='#f4f4f8' if t=='dark' else '#1b2140'
    PW=330;G=22;M=36
    W=M*2+5*PW+4*G
    rows=[PH[:5],PH[5:]]
    MW=(W-2*M-G)//2
    ims=[[rs(L(t,n),PW) for n,_ in r] for r in rows]
    mc=[rs(L(t,'mac-overview'),MW),rs(L(t,'mac-more'),MW)]
    H=120+sum(30+max(i.height for i in r)+G for r in ims)+30+max(i.height for i in mc)+M
    img=Image.new('RGB',(W,H),bg);d=ImageDraw.Draw(img)
    d.text((M,24),f'Sky Air · {t.upper()} · one-screen versions (draft mockups)',font=F(1,30),fill=fg)
    tx='EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE · NO ACCOUNTS CONNECTED, BUTTONS DO NOTHING · app frames 390x844 / 1440x900, no scrolling'
    tw=d.textlength(tx,font=F(1,15)); d.rounded_rectangle((M-8,64,M+tw+8,92),radius=14,fill='#15111d',outline='#fbbf24'); d.text((M,70),tx,font=F(1,15),fill='#fbbf24')
    y=108
    for r,row in zip(rows,ims):
        for i,(im,(n,lab)) in enumerate(zip(row,r)):
            x=M+i*(PW+G); d.text((x,y),lab,font=F(1,16),fill=fg); img.paste(im,(x,y+26))
        y+=30+max(i.height for i in row)+G
    for i,(im,lab) in enumerate(zip(mc,['Mac · Overview','Mac · Flags + Costs + Connect + Earnings'])):
        x=M+i*(MW+G); d.text((x,y),lab,font=F(1,16),fill=fg); img.paste(im,(x,y+26))
    img.save(f'{D}/clip-sky1-contact-{t}.png');print(t,img.size)
contact('light');contact('dark')
PW=430;G=40;M=40
ph=[rs(L('light','phone-overview'),PW),rs(L('dark','phone-overview'),PW)]
MW=2*PW+G
mc=[rs(L('light','mac-overview'),MW),rs(L('dark','mac-overview'),MW)]
W=M*2+2*PW+G
H=120+ph[0].height+G+sum(i.height+60 for i in mc)+M
img=Image.new('RGB',(W,H),'#10121c');d=ImageDraw.Draw(img)
d.text((M,24),'Sky Air · Light vs Dark · one-screen Overview',font=F(1,28),fill='#f4f4f8')
tx='Light / Dark switch visible top right · EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE'
tw=d.textlength(tx,font=F(0,16)); d.rounded_rectangle((M-8,60,M+tw+8,90),radius=14,fill='#15111d',outline='#fbbf24'); d.text((M,66),tx,font=F(0,16),fill='#fbbf24')
y=100
for i,(im,lab) in enumerate(zip(ph,['LIGHT','DARK'])):
    x=M+i*(PW+G); d.text((x,y),lab,font=F(1,18),fill='#cfd3ea'); img.paste(im,(x,y+28))
y+=28+ph[0].height+G
for im,lab in zip(mc,['LIGHT · Mac','DARK · Mac']):
    d.text((M,y),lab,font=F(1,18),fill='#cfd3ea'); img.paste(im,(M,y+28)); y+=28+im.height+G
img.crop((0,0,W,y)).save(f'{D}/clip-sky1-light-vs-dark.png')
