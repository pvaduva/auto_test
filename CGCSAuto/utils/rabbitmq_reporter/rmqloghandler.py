"""
rmqloghandler.py - RabbitMQ python log handler

Copyright (c) 2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

Adds RabbitMQ support to logging.
"""

"""
modification history:
---------------------
30sep16,dr   Fix connection timeout
23sep16,dr   version for XSTUDIO support in webapp. (Python2 support)
15sep16,dr   Add missing 'self' in timestampFormat
26aug16,dr   Created
"""

import logging
import pika
import time


class ConnectionError(Exception):
    pass 

class RMQHandler(logging.Handler):
    """ RabbitMQ log handler """

    rmqConnection = None

    def __init__(self, url='', host='127.0.0.1',
                 port=15672, user='guest', password='guest',
                 exchange='', routing_key='',
                 createExchange=False, exchangeType='direct',
                 prefix='', addTimestamp=False):
        """ create the instance and try to connect

        url : url to exchange server
        host : host IP address (if url not provided)
        port : port (if url not provided)
        user : user name (if url not provided)
        password : password (if url not provided)
        exchange : exchange to publish to
        routing_key : routing key for the message
        createExchange : Set to true to create an exchange
        exchangeType: exchange type (if createExchange true)
        prefix : Prefix to add to every message
        addTimeStamp : set to true to add time stamps.
        """

        try:
            super().__init__()
        except:
            super(RMQHandler, self).__init__()

        self.url = url
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.exchange = exchange
        self.routing_key = routing_key
        self.exchangeType = exchangeType
        self.prefix = prefix
        self.addTimestamp = addTimestamp
        self.rmqConnection = None

        self.timestampFormat = '[%12.2f]'

    def connect(self, createExchange=False):
        """ connect and create an exchange

        return True if all is well. False otherwise
        """

        try:
            if self.url:
                self.rmqConnection = pika.BlockingConnection(
                                     pika.connection.URLParameters(self.url))
            else:
                self.credentials = pika.PlainCredentials(self.user,
                                                         self.password)
                self.rmqConnection = pika.BlockingConnection(
                    pika.ConnectionParameters(host=self.host,
                                              port=self.port,
                                              credentials=self.credentials))
            self.channel = self.rmqConnection.channel()

            if createExchange:
                self.channel.exchange_declare(exchange=self.exchange,
                                              type=self.exchangeType)
            return True

        except pika.exceptions.ConnectionClosed:
            raise ConnectionError('Connection closed')

        return False

    def emit(self, record):
        """ emit the record """

        self.connect()

        if self.rmqConnection is None:
            return

        message = self.prefix + record
        if self.addTimestamp:
            message = "%s %s" % (self.timestampFormat % time.time(), message)

        self.channel = self.rmqConnection.channel()
        self.channel.basic_publish(exchange=self.exchange,
                                   routing_key=self.routing_key,
                                   body=message)

        self.rmqConnection.close()

