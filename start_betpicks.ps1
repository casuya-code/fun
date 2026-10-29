$env:PYTHONPATH="C:\Users\Admin\Desktop\Fun\backend"
Set-Location "C:\Users\Admin\Desktop\Fun\backend"
while($true){
  try { python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 }
  catch {}
  Start-Sleep -Seconds 5
}
