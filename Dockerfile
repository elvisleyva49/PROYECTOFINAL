
FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y gcc g++ unixodbc-dev

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]