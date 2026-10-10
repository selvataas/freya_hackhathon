# Builder tasarımı

Bu belge `builder/` altındaki builder'ın mimarisini anlatır. Kit dokümanları (`workflow-format.md`, `tools-and-code.md`, `api.md`) platformu anlatır; bu belge bizim onların üstüne ne kurduğumuzu.

## Kararlar

| Konu | Karar |
|---|---|
| CLI | `python3 builder/build.py <brief>... <openapi>`. Son argüman her zaman openapi. Tek brief + openapi mutlaka çalışır (teslim formatı). Brief yolu bir klasörse içindeki dosyalar ada göre sırayla okunur. Birden çok brief verilirse sırayla birleştirilir (ör. Brief B, Brief A'ya dayanır). |
| Slot | Her brief için ayrı slot. Slot adı son brief dosyasının adından türer (`brief-a.md` → `brief-a`, klasörse klasör adı). Her build kendi slotunu `freya.save_workflow` ile günceller ve yayınlar; yeni workflow açmaz. |
| Spec modeli | `claude-opus-5-5` (Anthropic SDK, `.venv` içinde Python 3.12). Bu model `temperature` kabul etmez ve düşünmesi kapatılamaz; tutarlılık sabit `effort`, iki paralel çıkarım + kod karşılaştırması, gerekirse uzlaştırma çağrısı ve brief hash'ine göre spec önbelleği (`cache/`) ile sağlanır. |
| Ajan modeli | `freya.AGENT_LLM`, değiştirilmez. |
| Brief'e özel değer | Builder kodunda brief'ten gelen hiçbir değer, kural, cümle veya isim yok. Kodda yalnızca builder'ın kendi sabit sözlükleri var (situation adları, tarih ifadeleri). |

## Akış

```
build.py <brief>... <openapi.json>
  1. tools_from_openapi()   openapi → araç tanımları (url, body yaprakları, enum'lar; customer_id sabitlenir)
  2. extract_spec()         LLM → spec.json (sabit şema), iki paralel çıkarım, gerekirse uzlaştırma
     validate_spec()        enum'lar openapi'de mi, birebir cümleler brief'te geçiyor mu, tarihler geçerli mi,
                            bantlar örtüşüyor/boşluk bırakıyor mu. Bilinmeyen sözlük değeri → en güvenli
                            davranış + trace uyarısı, asla çökme.
  3. render_workflow()      deterministik Python şablonu → workflow JSON. Code node'ları sabit bir Python
                            modülü + spec JSON'u (vars'a gömülür).
  4. dry-run → save_workflow(slot) (güncelle + yayınla)
  5. trace: traces/<ts>-<slot>.jsonl
```

## Temel karar: banka araçlarını motor çağırır, model değil

- Konuşma node'u konuşur ve müşterinin cevabından bir enum ve ham değerler çıkarır.
- Bir code node durum makinesi olarak bir sonraki adımı seçer (spec + durum).
- Banka araçları `api_request` node'larında `pre_actions` olarak, code'un yazdığı değişkenlerle sabitlenmiş değerlerle çalışır.
- `close_call` workflow düzeyinde `alwaysRunsAt: ["end_of_call"]` aracı; `outcome`/`reason` `{{final_outcome}}`/`{{final_reason}}` ile sabit. Değerler doluysa model çağrısı yapılmaz.
- Her araçta post-hook `what_to_do_next` ekler ve string bayraklar yazar.

Ürün id'si, tutar ve tarih modelin yazdığı argüman değildir; ikna sayacı koddadır; "kaydedildi" cümlesi ancak `ok:true` sonrası modelin talimatına girer.

## Workflow node grafı

```
setup (code, initial)          spec + now → takvim bilgileri, durum değişkenleri (sentinel)
greet (conversation)           tts: açılış + kimlik sorusu; extraction: presence
presence_decide (code)         → greet | id_ask | third_party | finish
third_party (conversation)     hesap bilgisi yok; extraction: callback günü/saati
cb_decide (code)               pencere kontrolü → do_callback | third_party | finish
do_callback (api_request)      schedule_callback
id_ask (conversation)          sıradaki soru code'dan; extraction: id_answer, id_reply_kind
id_decide (code)               normalizasyon, red sayacı → do_verify | id_ask | load_account | finish
do_verify (api_request)        verify_identity; post-hook id_state
load_account (api_request)     get_account
plan (code)                    ürün başına sözlü ad, bant, son tarih, floor, deneme planı; debt_facts
talk (conversation)            {{debt_facts}} + {{next_instruction}}; extraction: reply_kind, date_phrase, date, amount
decide (code)                  durum makinesi → talk | do_promise | do_note | do_transfer | finish
do_promise / do_note / do_transfer (api_request)
finish (code)                  situation + kayıtlar → final_outcome / final_reason
goodbye (conversation)         teşekkür + veda
hangup (end_call)
workflow tools: close_call (end_of_call, sabit değerler)
```

Kimlik öncesi node'ların (`greet`, `third_party`, `id_ask`) prompt'larında hesap bilgisi yoktur; `debt_facts` yalnızca `plan`'dan sonra oluşur. Rotalar `equals` ile; `matches_intent` kullanılmaz.

## system_prompt

Dil, kimlik, her yerde geçerli yasaklar, spec'ten gelen sabit cevaplar (AI, scam, bilgi yok) ve:

- **`unplaced_rules`**: şemaya oturmayan her kural, brief'teki birebir alıntısıyla system prompt'a da eklenir (yalnızca trace'e değil).

## Spesifikasyon şeması

Değerleri LLM doldurur. `*_text` alanları brief'ten birebir alınır ve doğrulanır. `situation` adları builder'ın sabit sözlüğüdür; LLM brief'in outcome/reason adlarını bunlara eşler.

Sabit sözlükler ve güvenli varsayılanlar (bilinmeyen değer gelirse):

| Sözlük | Değerler | Bilinmeyen değer → |
|---|---|---|
| situation | promise_recorded, already_paid, transfer_restructuring, transfer_human, transfer_support, refused, hardship, dispute, service_error, id_failed, id_declined, callback, no_callback, wrong_number, deceased, unclear | ilgili kural uygulanmaz; outcome tablosunda eşleşmeyen satır trace'e uyarı |
| deadline.unit | business_days, calendar_days, end_of_month | business_days |
| attempt.date | end_of_this_week, deadline, today, tomorrow | deadline |
| attempt.amount | full, floor, full_or_floor_if_too_much | full |
| non_business_in_range | offer_next_business_day, offer_previous_business_day, reject | offer_next_business_day |
| answer_type | date, digits, year, text | text (normalize etmeden gönder) |
| numeric_date_order | DMY, MDY, YMD | DMY |
| next_weekday | following_week, next_occurrence | following_week |

Şemanın tam hali `builder/spec_schema.py` içindedir. Ana bölümler: `meta`, `call_variables`, `phrases`, `forbidden`, `presence`, `third_party`, `identity`, `calendar`, `products`, `bands`, `promise_date`, `amounts`, `persuasion`, `hardship`, `confirmation`, `tool_failure`, `requests`, `outcomes`, `closing`, `multi_product`, `unplaced_rules`.

## Test

`run_cases.py --cases <dosya>` yalnızca mevcut vaka id'leriyle çalışır: mock servis ürünleri, kimliği, hataları ve `now`'u id'ye göre kendisi tutar (`unknown practice case`). Senaryo, checks ve expected bizim dosyamızdan gelir. Farklı takvim günü için `builder/test_cases.py` oturum değişkenlerine dosyadaki `variables.now` değerini yazar; mock tarihleri denetlemediği için bu geçerlidir.

## Trace

`traces/<ts>-<slot>.jsonl`: başlangıç/bitiş, her LLM çağrısı (model, tek satırlık amaç, token, süre), spec hash'i, uyarılar, workflow id/agent id/versiyon, dry-run sonucu, yapılan testler. `fak_…`, `sk-ant-…` ve team key değeri yazılmadan önce maskelenir.

## Kural eşlemesi

Brief A ve B'deki her kuralın tasarımda nerede karşılandığı (Y = yapısal, K = kod, P = prompt):

| # | Kural | Nerede | Tür |
|---|---|---|---|
| A1 | Açılış cümlesi, kimlik öncesi yasak kelimeler | `greet` tts; ön node'larda hesap bilgisi yok | Y+P |
| A2 | Kimlik sorusu | `greet` tts | Y |
| A3 | Net onay, 2 soru, unclear | `presence_decide` sayaç | K |
| A4 | Robot/AI | system_prompt | P |
| A5 | Üçüncü kişiye sebep yok | `third_party` (hesap bilgisi yok) | Y+P |
| A6 | Callback penceresi | `cb_decide` + `do_callback` | K |
| A7 | Pencere dışı → bir kez daha → no_callback | `cb_decide` | K |
| A8 | Yanlış numara | `presence` → `finish` | K |
| A9 | Vefat cümlesi | `goodbye` sabit cümle | Y |
| A10 | Akraba güvenlik sorusu cevaplayamaz | `third_party`'den verify'a yol yok | Y |
| A11 | Soru sırası, YYYY-MM-DD, GG-AA-YYYY | `id_decide` | K |
| A12 | Toplam 3 yanlış | post-hook + `id_decide` | K |
| A13 | day_month_swapped | post-hook | K |
| A14 | 3 yanlış → app/şube, failed | `finish` + `goodbye` | Y+K |
| A15 | Reddetme → declined | `id_decide` sayaç | K |
| A16 | İki soru geçince get_account | `load_account` erişimi | Y |
| A17 | Collections + ürün + tutar + gün | `plan` → `debt_facts` | K |
| A18 | Bant/son tarih | `plan` | K |
| A19 | Geçerli söz tarihi | `decide` | K |
| A20 | Hafta sonu/tatil → sonraki iş günü | `decide` | K |
| A21 | Belirsiz dönem | `decide` sayaç | K |
| A22 | next/this weekday | `decide.resolve_phrase` | K |
| A23 | Son tarihten sonra → son tarih | `decide` | K |
| A24 | Önce tam tutar, "ne kadar" sorulmaz | `decide` + system_prompt | K+P |
| A25 | Floor alanı | `plan` | K |
| A26 | Fazla → floor bir kez + uyarı | `decide` | K |
| A27 | Önerilen tutar aralığı | `decide` | K |
| A28 | "Bugün ödeyebilir misiniz?" | `decide` | K |
| A29 | Öneri ret değildir | `decide` önceliği | K |
| A30 | Deneme planı | `plan` + `decide` | K |
| A31 | Denemeler bitince refused | `decide` | K |
| A32 | Hardship | `decide` + `do_transfer` | K |
| A33 | İndirim/plan yok | system_prompt | P |
| A34 | Okuma + onay → create | `decide` → `do_promise` | K |
| A35 | Onayda değişiklik | `decide` | K |
| A36 | Ürün başına bir söz | `decide` | K |
| A37 | ok:true sonrası "kaydedildi", 1 tekrar, service_error | post-hook + `decide` | K |
| A38 | SMS cümlesi | `decide` talimatı | K |
| A39 | Zaten ödedim | `decide` → `finish` | K |
| A40 | İtiraz | `decide` | K |
| A41 | Yeniden yapılandırma | `decide` → `do_transfer` | K |
| A42 | İnsan isteği | `decide` / `id_decide` sayaç | K |
| A43 | Scam | system_prompt | P |
| A44 | Bilinmeyen soru | system_prompt | P |
| A45 | İki kez konuşmak istemiyorum | `decide` / `id_decide` | K |
| A46 | Tek close_call, outcome tablosu | `finish` + end_of_call | Y+K |
| A47 | Teşekkür + veda | `goodbye` | Y |
| B1–B5 | Çoklu ürün, ürün başına bant/deneme, sıra | `plan` + `decide` | K |
| B6 | Tek tarih son tarihi aşarsa kırp | `decide` | K |
| B7 | Tek okuma, tek onay, ürün başına create | `decide` → `do_promise` döngüsü | K |
| B8 | Sözsüz ürüne add_note | `decide` → `do_note` döngüsü | K |
| B9 | Ürün bazında itiraz/ödeme çağrıyı bitirmez | `decide` | K |
| B10 | Transfer: kaydedilen kalır, not yok | `decide` | K |
| B11 | Başarısız söz → service_error notu | `decide` | K |
| B-kapanış | paid / ilk not reason / promise | `finish` | K |
