# Użyj oficjalnego obrazu Python
FROM python:3.10-slim

# Ustaw katalog roboczy w kontenerze
WORKDIR /app

# Skopiuj plik zależności
COPY requirements.txt .

# Zainstaluj zależności
# --no-cache-dir oszczędza miejsce
RUN pip install --no-cache-dir -r requirements.txt

# Skopiuj kod aplikacji do kontenera
COPY main.py .

# Ustaw port, na którym będzie działać aplikacja
EXPOSE 8000

# Polecenie uruchamiające aplikację przy starcie kontenera
# Używamy 0.0.0.0, aby aplikacja była dostępna z zewnątrz kontenera
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

