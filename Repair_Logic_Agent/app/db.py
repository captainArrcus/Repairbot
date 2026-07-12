import psycopg

from app import config


def connect() -> psycopg.Connection:
    # ponytail: connection per request; psycopg_pool when load demands it
    return psycopg.connect(config.DATABASE_URL)
