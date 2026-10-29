FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home luxblox && mkdir /data && chown luxblox:luxblox /data
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY --chown=luxblox:luxblox server /app/server
COPY --chown=luxblox:luxblox config /app/config
COPY --chown=luxblox:luxblox places /app/places
USER luxblox
ENV LUXBLOX_HOST=0.0.0.0 LUXBLOX_DATABASE=/data/luxblox.sqlite3 PORT=8080
EXPOSE 8080
CMD ["python3", "-m", "server.app"]

