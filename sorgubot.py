import asyncio
import aiohttp
import re
import os
from typing import Callable, Dict, Any, Awaitable
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Bot token'ınızı buraya yazın
BOT_TOKEN = "8528601189:AAGee6LDW2uNjOL4Uv_I2PPBNS9973Ob4Bo"
API_BASE = "https://arastir.vip/api"

# --- ZORUNLU KANAL AYARLARI ---
CHANNEL_USERNAME = "@tuzlalisorgubot" # Kanalın @kullanıcıadı
CHANNEL_LINK = "https://t.me/tuzlalisorgubot" # Kanalın davet linki

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- ZORUNLU ABONELİK KONTROLÜ (MIDDLEWARE) ---
class ForceSubMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user_id = None
        if isinstance(event, types.Message):
            user_id = event.from_user.id
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
            # Kullanıcı "Katıldım" butonuna basıyorsa kontrol etmeden butonu çalıştır
            if event.data == "check_sub_callback":
                return await handler(event, data)
        
        if user_id:
            _bot: Bot = data.get('bot')
            try:
                member = await _bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
                
                # Aiogram 3.x versiyonu uyumluluğu için member.status.value kontrolü eklendi
                status = getattr(member.status, "value", member.status)
                
                # Eğer kullanıcı üye, admin veya kurucu değilse engelle
                if status not in ["member", "administrator", "creator", "restricted"]:
                    markup = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📢 Kanala Katıl", url=CHANNEL_LINK)],
                        [InlineKeyboardButton(text="✅ Katıldım (Sorgula)", callback_data="check_sub_callback")]
                    ])
                    
                    mesaj_metni = "⚠️ <b>Botu kullanabilmek için öncelikle kanalımıza katılmalısınız.</b>\nLütfen aşağıdan kanala katılıp 'Katıldım' butonuna tıklayın."
                    
                    if isinstance(event, types.Message):
                        await event.answer(mesaj_metni, reply_markup=markup, parse_mode="HTML")
                    elif isinstance(event, types.CallbackQuery):
                        await event.message.answer(mesaj_metni, reply_markup=markup, parse_mode="HTML")
                        await event.answer()
                    return # Kullanıcı kanalda değilse alt işlemleri durdur
            except Exception as e:
                print(f"Kanal kontrol hatası (Bot kanalda yönetici mi?): {e}")
                # Hata alınırsa (örneğin bot yönetici değilse) botun tamamen çökmemesi için geçişe izin verebiliriz
                # veya aşağıdaki pass'i kaldırıp return ile sistemi durdurabiliriz. Şimdilik çalışmaya devam eder.
                pass
        
        return await handler(event, data)

# Middleware'leri Dispatcher'a kaydediyoruz
dp.message.middleware(ForceSubMiddleware())
dp.callback_query.middleware(ForceSubMiddleware())

# --- KATILDIM BUTONU İŞLEYİCİSİ ---
@dp.callback_query(F.data == "check_sub_callback")
async def check_sub_btn(callback: types.CallbackQuery, state: FSMContext):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=callback.from_user.id)
        status = getattr(member.status, "value", member.status)
        
        if status in ["member", "administrator", "creator", "restricted"]:
            await callback.message.delete()
            await callback.message.answer(
                "✅ Kanala başarıyla katıldınız! Botu kullanabilirsiniz.\n\nAşağıdan işleminizi seçiniz:", 
                reply_markup=ana_menu()
            )
        else:
            await callback.answer("❌ Henüz kanala katılmamışsınız! Lütfen katılıp tekrar deneyin.", show_alert=True)
    except Exception as e:
        print(f"Kontrol hatası: {e}")
        await callback.answer("⚠️ Kontrol yapılamadı. Lütfen botun kanalda yönetici olduğundan emin olun.", show_alert=True)


# Sorgulama durumları
class SorguStates(StatesGroup):
    tc_bekleniyor = State()
    adsoyad_ad = State()
    adsoyad_soyad = State()
    adsoyad_il = State()
    adsoyad_ilce = State()
    gsm_bekleniyor = State()

# Ana menü
def ana_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 TC Sorgula", callback_data="sorgu_tc")],
        [InlineKeyboardButton(text="👤 Ad Soyad Sorgula", callback_data="sorgu_adsoyad")],
        [InlineKeyboardButton(text="📱 TC'den GSM", callback_data="sorgu_tcgsm")],
        [InlineKeyboardButton(text="📞 GSM'den TC", callback_data="sorgu_gsmtc")],
        [InlineKeyboardButton(text="🏢 İşyeri Bilgisi", callback_data="sorgu_isyeri")],
        [InlineKeyboardButton(text="🏠 Adres Bilgisi", callback_data="sorgu_adres")],
        [InlineKeyboardButton(text="👨‍👩‍👧‍👦 Sulale Ağacı", callback_data="sorgu_sulale")],
        [InlineKeyboardButton(text="❓ Yardım", callback_data="yardim")]
    ])
    return keyboard

# Gönderim Seçenekleri
def gonderim_secenekleri():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Direkt Mesaj", callback_data="secim_mesaj")],
        [InlineKeyboardButton(text="📄 TXT Dosyası", callback_data="secim_txt")]
    ])

# API isteği gönderme
async def api_get(endpoint, params):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/{endpoint}", params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.json(content_type=None)
                return None
    except Exception as e:
        print(f"API hatası: {e}")
        return None

# Success kontrolü için yardımcı fonksiyon
def is_success(sonuc):
    if not sonuc:
        return False
    status = sonuc.get("success", "")
    return str(status).lower() in ["true", "1"] or status is True

# /start komutu
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"Merhaba {message.from_user.first_name}! 👋\n\n"
        "Ben bir sorgulama botuyum. Aşağıdaki butonlardan yapmak istediğiniz sorguyu seçebilirsiniz.\n\n"
        "💡 İpucu: /menu yazarak ana menüye dönebilirsiniz.",
        reply_markup=ana_menu()
    )

# /menu komutu
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("Ne yapmak istersiniz?", reply_markup=ana_menu())

# Yardım
@dp.callback_query(F.data == "yardim")
async def yardim_callback(callback: types.CallbackQuery):
    yardim_text = (
        "📖 Kullanım Kılavuzu\n\n"
        "🔍 TC Sorgula: TC kimlik no ile kişi bilgisi\n"
        "👤 Ad Soyad Sorgula: İsimle kişi arama\n"
        "📱 TC'den GSM: TC'ye kayıtlı telefonları göster\n"
        "📞 GSM'den TC: Telefon numarasının sahibi\n"
        "🏢 İşyeri Bilgisi: Çalışılan şirket bilgileri\n"
        "🏠 Adres Bilgisi: Kayıtlı adres bilgileri\n"
        "👨‍👩‍👧‍👦 Sulale Ağacı: Aile bireylerini göster\n\n"
        "Herhangi bir sorunuz varsa @destek yazabilirsiniz."
    )
    await callback.message.edit_text(yardim_text, parse_mode="HTML", reply_markup=ana_menu())
    await callback.answer()

# ---------- TXT / MESAJ SEÇİM İŞLEYİCİLERİ ----------

@dp.callback_query(F.data == "secim_mesaj")
async def secim_mesaj_gonder(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    metin = data.get("sonuc_metni")
    
    if metin:
        if len(metin) > 4000:
            for i in range(0, len(metin), 4000):
                await callback.message.answer(metin[i:i+4000], parse_mode="HTML")
            await callback.message.answer("✅ Tüm sonuçlar listelendi.", reply_markup=ana_menu())
            await callback.message.delete()
        else:
            await callback.message.edit_text(metin, parse_mode="HTML", reply_markup=ana_menu())
    else:
        await callback.message.edit_text("❌ Veri bulunamadı veya süre doldu.", reply_markup=ana_menu())
    await state.clear()

@dp.callback_query(F.data == "secim_txt")
async def secim_txt_gonder(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    metin = data.get("sonuc_metni")
    
    if metin:
        temiz_metin = re.sub(r'<[^>]+>', '', metin)
        dosya = BufferedInputFile(temiz_metin.encode('utf-8'), filename="sorgu_sonucu.txt")
        await callback.message.answer_document(document=dosya, caption="✅ Sonuçlarınız TXT dosyası olarak oluşturuldu.", reply_markup=ana_menu())
        await callback.message.delete()
    else:
        await callback.message.edit_text("❌ Veri bulunamadı veya süre doldu.", reply_markup=ana_menu())
    await state.clear()

# Yönlendirmeli TC Sorgulama Başlatıcıları
@dp.callback_query(F.data == "sorgu_tc")
async def tc_sorgu_baslat(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("TC kimlik numarasını girin (11 haneli):")
    await state.set_state(SorguStates.tc_bekleniyor)
    await state.update_data(sorgu_tipi="tc")
    await callback.answer()

@dp.callback_query(F.data == "sorgu_tcgsm")
async def tcgsm_sorgu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("TC kimlik numarasını girin:")
    await state.set_state(SorguStates.tc_bekleniyor)
    await state.update_data(sorgu_tipi="tcgsm")
    await callback.answer()

@dp.callback_query(F.data == "sorgu_isyeri")
async def isyeri_sorgu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("TC kimlik numarasını girin:")
    await state.set_state(SorguStates.tc_bekleniyor)
    await state.update_data(sorgu_tipi="isyeri")
    await callback.answer()

@dp.callback_query(F.data == "sorgu_adres")
async def adres_sorgu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("TC kimlik numarasını girin:")
    await state.set_state(SorguStates.tc_bekleniyor)
    await state.update_data(sorgu_tipi="adres")
    await callback.answer()

@dp.callback_query(F.data == "sorgu_sulale")
async def sulale_sorgu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("TC kimlik numarasını girin:")
    await state.set_state(SorguStates.tc_bekleniyor)
    await state.update_data(sorgu_tipi="sulale")
    await callback.answer()

# TC İşleyici 
@dp.message(SorguStates.tc_bekleniyor)
async def tc_sorgu_isle(message: types.Message, state: FSMContext):
    tc = message.text.strip()
    
    if not tc.isdigit() or len(tc) != 11:
        await message.answer("❌ Hatalı format! TC numarası 11 haneli olmalıdır.")
        return
    
    data = await state.get_data()
    sorgu_tipi = data.get("sorgu_tipi", "tc")
    
    await message.answer("🔍 Sorgulanıyor, lütfen bekleyin...")
    
    # Sorgu tipine göre endpoint belirleme
    endpoint = "tc.php"
    if sorgu_tipi == "tcgsm": endpoint = "tcgsm.php"
    elif sorgu_tipi == "isyeri": endpoint = "isyeri.php"
    elif sorgu_tipi == "adres": endpoint = "adres.php"
    elif sorgu_tipi == "sulale": endpoint = "sulale.php"
    
    sonuc = await api_get(endpoint, {"tc": tc})
    
    if is_success(sonuc):
        if sorgu_tipi == "tc":
            cevap = (
                f"✅ Kişi Bilgileri\n\n"
                f"👤 Ad Soyad: {sonuc.get('ADI', '-')} {sonuc.get('SOYADI', '-')}\n"
                f"🆔 TC: {sonuc.get('TC', '-')}\n"
                f"🎂 Doğum Tarihi: {sonuc.get('DOGUMTARIHI', '-')}\n"
                f"📍 Nüfus: {sonuc.get('NUFUSIL', '-')} / {sonuc.get('NUFUSILCE', '-')}\n"
                f"👩 Anne Adı: {sonuc.get('ANNEADI', '-')} (TC: {sonuc.get('ANNETC', '-')})\n"
                f"👨 Baba Adı: {sonuc.get('BABAADI', '-')} (TC: {sonuc.get('BABATC', '-')})\n"
                f"🌍 Uyruk: {sonuc.get('UYRUK', '-')}"
            )
        else:
            cevap = f"✅ Sonuçlar ({sorgu_tipi.upper()}):\n\n"
            kayitlar = sonuc.get("data", sonuc) 
            
            if isinstance(kayitlar, list):
                for i, k in enumerate(kayitlar[:20], 1): 
                    cevap += f"--- Kayıt {i} ---\n"
                    if isinstance(k, dict):
                        for key, val in k.items():
                            cevap += f"{key}: {val}\n"
                    cevap += "\n"
            elif isinstance(kayitlar, dict):
                for key, val in kayitlar.items():
                    if key not in ["success", "message"]:
                        cevap += f"{key}: {val}\n"
            else:
                cevap += str(kayitlar)

        await state.update_data(sonuc_metni=cevap)
        await message.answer("✅ Kayıt bulundu! Sonucu nasıl almak istersiniz?", reply_markup=gonderim_secenekleri())
    else:
        await message.answer("❌ Kayıt bulunamadı veya API yanıt vermedi.", reply_markup=ana_menu())
        await state.clear()

# Ad Soyad Sorgulama
@dp.callback_query(F.data == "sorgu_adsoyad")
async def adsoyad_sorgu_baslat(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Kişinin adını girin:")
    await state.set_state(SorguStates.adsoyad_ad)
    await callback.answer()

@dp.message(SorguStates.adsoyad_ad)
async def adsoyad_ad_al(message: types.Message, state: FSMContext):
    await state.update_data(adi=message.text.strip())
    await message.answer("Şimdi soyadını girin:")
    await state.set_state(SorguStates.adsoyad_soyad)

@dp.message(SorguStates.adsoyad_soyad)
async def adsoyad_soyad_al(message: types.Message, state: FSMContext):
    await state.update_data(soyadi=message.text.strip())
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Direkt Sorgula", callback_data="adsoyad_direkt")],
        [InlineKeyboardButton(text="🗺 İl Ekle", callback_data="adsoyad_il_ekle")]
    ])
    
    await message.answer("Filtreleme yapmak ister misiniz?", reply_markup=keyboard)

@dp.callback_query(F.data == "adsoyad_direkt")
async def adsoyad_direkt_sorgu(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text("🔍 Sorgulanıyor...")
    
    sonuc = await api_get("adsoyad.php", {"adi": data['adi'], "soyadi": data['soyadi']})
    
    if is_success(sonuc):
        kayitlar = sonuc.get("data", [])
        if len(kayitlar) > 10:
            cevap = f"✅ {len(kayitlar)} kayıt bulundu\n\nİlk 10 kayıt gösteriliyor:\n\n"
            kayitlar = kayitlar[:10]
        else:
            cevap = f"✅ {len(kayitlar)} kayıt bulundu:\n\n"
        
        for i, k in enumerate(kayitlar, 1):
            cevap += (
                f"{i}. {k.get('ADI', '-')} {k.get('SOYADI', '-')}\n"
                f"   TC: {k.get('TC', '-')}\n"
                f"   📍 {k.get('NUFUSIL', '-')} / {k.get('NUFUSILCE', '-')}\n\n"
            )
        
        await state.update_data(sonuc_metni=cevap)
        await callback.message.edit_text("✅ Kayıt bulundu! Sonucu nasıl almak istersiniz?", reply_markup=gonderim_secenekleri())
    else:
        await callback.message.edit_text("❌ Kayıt bulunamadı.", reply_markup=ana_menu())
        await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "adsoyad_il_ekle")
async def adsoyad_il_ekle(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("İl adını girin:")
    await state.set_state(SorguStates.adsoyad_il)
    await callback.answer()

@dp.message(SorguStates.adsoyad_il)
async def adsoyad_il_al(message: types.Message, state: FSMContext):
    await state.update_data(il=message.text.strip())
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sorgula", callback_data="adsoyad_il_sorgu")],
        [InlineKeyboardButton(text="🏘 İlçe Ekle", callback_data="adsoyad_ilce_ekle")]
    ])
    
    await message.answer("İlçe de eklemek ister misiniz?", reply_markup=keyboard)

@dp.callback_query(F.data == "adsoyad_ilce_ekle")
async def adsoyad_ilce_ekle(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("İlçe adını girin:")
    await state.set_state(SorguStates.adsoyad_ilce)
    await callback.answer()

@dp.message(SorguStates.adsoyad_ilce)
async def adsoyad_ilce_al(message: types.Message, state: FSMContext):
    await state.update_data(ilce=message.text.strip())
    data = await state.get_data()
    
    await message.answer("🔍 Sorgulanıyor...")
    
    params = {"adi": data['adi'], "soyadi": data['soyadi'], "il": data['il'], "ilce": data['ilce']}
    sonuc = await api_get("adsoyad.php", params)
    
    if is_success(sonuc):
        kayitlar = sonuc.get("data", [])
        cevap = f"✅ {len(kayitlar)} kayıt bulundu:\n\n"
        
        for i, k in enumerate(kayitlar[:10], 1):
            cevap += (
                f"{i}. {k.get('ADI', '-')} {k.get('SOYADI', '-')}\n"
                f"   TC: {k.get('TC', '-')}\n"
                f"   📍 {k.get('NUFUSIL', '-')} / {k.get('NUFUSILCE', '-')}\n\n"
            )
        
        await state.update_data(sonuc_metni=cevap)
        await message.answer("✅ Kayıt bulundu! Sonucu nasıl almak istersiniz?", reply_markup=gonderim_secenekleri())
    else:
        await message.answer("❌ Kayıt bulunamadı.", reply_markup=ana_menu())
        await state.clear()

@dp.callback_query(F.data == "adsoyad_il_sorgu")
async def adsoyad_il_sorgu(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text("🔍 Sorgulanıyor...")
    
    params = {"adi": data['adi'], "soyadi": data['soyadi'], "il": data['il']}
    sonuc = await api_get("adsoyad.php", params)
    
    if is_success(sonuc):
        kayitlar = sonuc.get("data", [])
        cevap = f"✅ {len(kayitlar)} kayıt bulundu:\n\n"
        
        for i, k in enumerate(kayitlar[:10], 1):
            cevap += (
                f"{i}. {k.get('ADI', '-')} {k.get('SOYADI', '-')}\n"
                f"   TC: {k.get('TC', '-')}\n"
                f"   📍 {k.get('NUFUSIL', '-')} / {k.get('NUFUSILCE', '-')}\n\n"
            )
        
        await state.update_data(sonuc_metni=cevap)
        await callback.message.edit_text("✅ Kayıt bulundu! Sonucu nasıl almak istersiniz?", reply_markup=gonderim_secenekleri())
    else:
        await callback.message.edit_text("❌ Kayıt bulunamadı.", reply_markup=ana_menu())
        await state.clear()
    await callback.answer()

# GSM'den TC
@dp.callback_query(F.data == "sorgu_gsmtc")
async def gsmtc_sorgu_baslat(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("GSM numarasını girin (5551234567):")
    await state.set_state(SorguStates.gsm_bekleniyor)
    await callback.answer()

@dp.message(SorguStates.gsm_bekleniyor)
async def gsmtc_sorgu_isle(message: types.Message, state: FSMContext):
    gsm = message.text.strip()
    
    if not gsm.isdigit() or len(gsm) != 10:
        await message.answer("❌ Hatalı format! GSM 10 haneli olmalıdır (5551234567)")
        return
    
    await message.answer("🔍 Sorgulanıyor...")
    
    sonuc = await api_get("gsmtc.php", {"gsm": gsm})
    
    if is_success(sonuc):
        cevap = (
            f"✅ Numara Sahibi\n\n"
            f"📱 GSM: {gsm}\n"
            f"👤 Ad Soyad: {sonuc.get('ADI', '-')} {sonuc.get('SOYADI', '-')}\n"
            f"🆔 TC: {sonuc.get('TC', '-')}"
        )
        await state.update_data(sonuc_metni=cevap)
        await mess