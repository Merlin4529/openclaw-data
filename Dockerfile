FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install requests pandas numpy
CMD ["python3", "railway_daily_pipeline.py"]
