"""
Registry of SQS message handlers.

"""
from abc import ABCMeta, abstractproperty
from inspect import isclass

from microcosm.api import defaults
from microcosm.errors import NotBoundError
from microcosm_logging.decorators import logger

from microcosm_pubsub.codecs import PubSubMessageCodec


class AlreadyRegisteredError(Exception):
    pass


class Registry(object):
    """
    A decorator-friendly registry of per-media type objects.

    Supports static configuration from binding keys and explicit registration from decorators
    (using a singleton).

    """
    __metaclass__ = ABCMeta

    def __init__(self, graph):
        """
        Create registry, auto-registering items found using the legacy graph binding key.

        """
        self.graph = graph

        # legacy graph handling
        try:
            for media_type, value in getattr(graph, self.legacy_binding_key).items():
                self.register(media_type, value)
        except NotBoundError:
            pass
        # legacy config handling
        try:
            for media_type, value in getattr(graph.config, self.legacy_binding_key).get("mappings").items():
                self.register(media_type, value)
        except AttributeError:
            pass

    @abstractproperty
    def legacy_binding_key(self):
        pass

    @classmethod
    def register(cls, media_type, value):
        """
        Register a value for a media type.

        It is an error to register more than one value for the same media type.

        """
        existing_value = cls.MAPPINGS.get(media_type)
        if existing_value:
            if value == existing_value:
                return
            raise AlreadyRegisteredError("A mapping already exists  media type: {}".format(
                media_type,
            ))
        cls.MAPPINGS[media_type] = value

    @classmethod
    def keys(cls):
        return cls.MAPPINGS.keys()


@logger
class PubSubMessageSchemaRegistry(Registry):
    """
    Keeps track of available message schemas.

    """
    # singleton registry
    MAPPINGS = dict()

    def __init__(self, graph):
        super(PubSubMessageSchemaRegistry, self).__init__(graph)
        self.strict = graph.config.pubsub_message_schema_registry.strict

    @property
    def legacy_binding_key(self):
        return "pubsub_message_codecs"

    def __getitem__(self, media_type):
        """
        Create a codec or raise KeyError.

        """
        schema_cls = self.__class__.MAPPINGS[media_type]
        return PubSubMessageCodec(schema_cls(strict=self.strict))


@logger
class SQSMessageHandlerRegistry(Registry):
    """
    Keeps track of available handlers.

    """
    # singleton registry
    MAPPINGS = dict()

    @property
    def legacy_binding_key(self):
        return "sqs_message_handlers"

    def __getitem__(self, media_type):
        """
        Create a handler or raise KeyError.

        """
        handler = self.__class__.MAPPINGS[media_type]
        if isclass(handler):
            return handler(self.graph)
        else:
            return handler


@defaults(
    strict=True,
)
def configure_schema_registry(graph):
    return PubSubMessageSchemaRegistry(graph)


def configure_handler_registry(graph):
    return SQSMessageHandlerRegistry(graph)


def media_type_for(schema_cls):
    if hasattr(schema_cls, "MEDIA_TYPE"):
        return schema_cls.MEDIA_TYPE
    if hasattr(schema_cls, "infer_media_type"):
        return schema_cls.infer_media_type()
    raise Exception("Cannot infer media type for schema class: {}".format(schema_cls))


def register_schema(schema_cls):
    PubSubMessageSchemaRegistry.register(media_type_for(schema_cls), schema_cls)


def register_handler(schema_cls, handler):
    SQSMessageHandlerRegistry.register(media_type_for(schema_cls), handler)
