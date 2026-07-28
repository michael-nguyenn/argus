import pika
import logging
import time
import json

MAX_ATTEMPTS = 5
SLEEP = 2
logger = logging.getLogger("argus.queue")

class JobQueue:
    def __init__(self, url: str):
        self.url = url
        self.conn = None
        self.channel = None
        self._connect()

    def publish(self, queue_name: str, message: dict):
        self.channel.queue_declare(queue=queue_name, durable=True)
        self.channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(message).encode()
        )

    def consume(self, queue_name: str) -> tuple[dict, int] | None:
        self.channel.queue_declare(queue=queue_name, durable=True)

        # all three are None when queue is empty
        method, properties, body = self.channel.basic_get(queue=queue_name, auto_ack=False)

        if method is None:
            return None

        message = json.loads(body.decode())

        return (message, method.delivery_tag)

    def ack(self, delivery_tag):
        # tells Rabbit the delivery is done
        self.channel.basic_ack(delivery_tag=delivery_tag)

    def depth(self, queue_name: str) -> int:
        result = self.channel.queue_declare(queue=queue_name, durable=True, passive=True)
        return result.method.message_count

    def _connect(self):
        for i in range(MAX_ATTEMPTS):
            try:
                self.conn = pika.BlockingConnection(pika.URLParameters(self.url))
                self.channel = self.conn.channel()
                self.channel.basic_qos(prefetch_count=1)
                logger.info("Connected")
                return
            except pika.exceptions.AMQPConnectionError:
                logger.error(f"attempt {i + 1} failed, retrying in {SLEEP} seconds")
                time.sleep(SLEEP)

        raise ConnectionError(f"could not connect to RabbitMQ at {self.url}")