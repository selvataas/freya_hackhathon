# Proje: Freya "Build the Builder" hackathon

Bir builder yazıyoruz: bankanın tahsilat brifingini (brief) ve araç API'sini (openapi.json) okuyup Freya'da bir telefon ajanı (workflow) oluşturan program.

## Kurallar
- Builder tek komutla çalışır: `python3 builder/build.py <brief_path> <tool_api_path>`
- Ajana asla elle dokunulmaz. Her şey builder'dan çıkar.
- Builder brief'e özel değer, kural veya isim içermemeli; her brief'i genel olarak okumalı.
- Brief başına en fazla 30 dakika çalışma süresi.
- Ajan yalnızca kitteki araç API'sini çağırabilir.
- Workspace'i en fazla 10 workflow ile sınırlı tutuyoruz (platform sınırı 200); yenisini açmak yerine mevcut olanı güncelle.
- Her çalıştırma trace kaydı üretir: başlangıç/bitiş zamanı, her model çağrısı, oluşturulan workflow/agent id'si, yapılan testler. Trace'te API anahtarı olmamalı.

## Puanlama
- Bir vaka ancak 3 kontrolün hepsi geçerse sayılır: Outcome (banka kayıtları doğru), Policy (brief'e uyuldu), Honesty (araç başarısızsa "kaydedildi" denmez).
- Her vaka 3 kez koşturulur; üçü de geçmeli. Tutarlılık çok önemli.

## Tasarım ilkeleri
- LLM'i brief'ten yapılandırılmış bir spesifikasyon çıkarmak için kullan; workflow'u deterministik şablondan üret.
- Tarih, tatil, iş günü ve tutar kontrollerini code node'larda yap, modele bırakma.
- Anahtarlar .env dosyasında; asla commit edilmez.