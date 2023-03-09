FROM python:3.8

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./*.py ./

CMD [ "uvicorn", "main:app", "--port", "51235", "--host", "0.0.0.0" ]