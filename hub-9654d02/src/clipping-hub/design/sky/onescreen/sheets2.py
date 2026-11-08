from PIL import Image, ImageDraw, ImageFont
import os
D=os.path.dirname(os.path.abspath(__file__))
F=lambda b,s: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf'%('-Bold' if b else ''),s)
L=lambda t,n: Image.open(f'{D}/clip-sky2-{t}-{n}.png')
def rs(im,w): return im.resize((w,int(im.height*w/im.width)),Image.LANCZOS)
for t in ('light','dark'):
    bg='#0b0d16' if t=='dark' else '#eef1fb'; fg='#f4f4f8' if t=='dark' else '#1b2140'
    PW=430;G=30;M=40;W=M*2+3*PW+2*G
    names=[('phone-overview-pooled','a · Overview + pooled card'),('phone-pooled-split','b · Tapped: split'),('phone-pooled-example','c · DEMO (example figures)')]
    ph=[rs(L(t,n),PW) for n,_ in names]; mac=rs(L(t,'mac-overview-pooled'),W-2*M)
    H=120+30+max(i.height for i in ph)+G+30+mac.height+M
    img=Image.new('RGB',(W,H),bg);d=ImageDraw.Draw(img)
    d.text((M,24),f'Sky Air · {t.upper()} · pooled revenue card (draft mockups)',font=F(1,28),fill=fg)
    tx='EXAMPLE DATA · DRAFT MOCKUP · NOT LIVE · NO ACCOUNTS CONNECTED, BUTTONS DO NOTHING'
    tw=d.textlength(tx,font=F(1,15)); d.rounded_rectangle((M-8,66,M+tw+8,94),radius=14,fill='#15111d',outline='#fbbf24'); d.text((M,72),tx,font=F(1,15),fill='#fbbf24')
    y=118
    for i,(im,(n,lab)) in enumerate(zip(ph,names)):
        x=M+i*(PW+G); d.text((x,y),lab,font=F(1,14),fill=fg); img.paste(im,(x,y+28))
    y+=28+max(i.height for i in ph)+G
    d.text((M,y),'d · Mac overview with pooled revenue card',font=F(1,16),fill=fg); img.paste(mac,(M,y+28))
    img.save(f'{D}/clip-sky2-contact-{t}.png'); print(t,img.size)
