import re
import warnings
import ast
import json
from pathlib import Path
import urllib.parse
from os import environ
from functools import partial
from django.core.exceptions import ImproperlyConfigured


def _cast(value):
    # Safely evaluate an expression node or a string containing a Python
    # literal or container display.
    # https://docs.python.org/3/library/ast.html#ast.literal_eval
    try:
        return ast.literal_eval(value)
    except ValueError:
        return value

# return int if possible
def _cast_int(v):
    return int(v) if hasattr(v, 'isdigit') and v.isdigit() else v


def _cast_urlstr(v):
    return urllib.parse.unquote_plus(v) if isinstance(v, str) else v


class BaseLoader:

    URL_CLASS = urllib.parse.ParseResult
    PATH_CLASS = Path


    BOOLEAN_TRUE_STRINGS = ('true', 'on', 'ok', 'y', 'yes', '1')

    DB_SCHEMES = {
        'postgres': 'django.db.backends.postgresql',
        'postgresql': 'django.db.backends.postgresql',
        'psql': 'django.db.backends.postgresql',
        'pgsql': 'django.db.backends.postgresql',
        'postgis': 'django.contrib.gis.db.backends.postgis',
        'mysql': 'django.db.backends.mysql',
        'mysql2': 'django.db.backends.mysql',
        'mysqlgis': 'django.contrib.gis.db.backends.mysql',
        'oracle': 'django.db.backends.oracle',
        'spatialite': 'django.contrib.gis.db.backends.spatialite',
        'sqlite': 'django.db.backends.sqlite3',
    }
    _DB_BASE_OPTIONS = ['CONN_MAX_AGE', 'ATOMIC_REQUESTS', 'AUTOCOMMIT', 'DISABLE_SERVER_SIDE_CURSORS']

    CACHE_SCHEMES = {
        'dbcache': 'django.core.cache.backends.db.DatabaseCache',
        'dummycache': 'django.core.cache.backends.dummy.DummyCache',
        'filecache': 'django.core.cache.backends.filebased.FileBasedCache',
        'locmemcache': 'django.core.cache.backends.locmem.LocMemCache',
        'memcache': 'django.core.cache.backends.memcached.MemcachedCache',
        'pymemcache': 'django.core.cache.backends.memcached.PyLibMCCache',
    }
    _CACHE_BASE_OPTIONS = ['TIMEOUT', 'KEY_PREFIX', 'VERSION', 'KEY_FUNCTION', 'BINARY']

    EMAIL_SCHEMES = {
        'smtp': 'django.core.mail.backends.smtp.EmailBackend',
        'smtps': 'django.core.mail.backends.smtp.EmailBackend',
        'smtp+tls': 'django.core.mail.backends.smtp.EmailBackend',
        'smtp+ssl': 'django.core.mail.backends.smtp.EmailBackend',
        'consolemail': 'django.core.mail.backends.console.EmailBackend',
        'filemail': 'django.core.mail.backends.filebased.EmailBackend',
        'memorymail': 'django.core.mail.backends.locmem.EmailBackend',
        'dummymail': 'django.core.mail.backends.dummy.EmailBackend'
    }
    _EMAIL_BASE_OPTIONS = ['EMAIL_USE_TLS', 'EMAIL_USE_SSL']

    class NOTSET:
        pass

    def __init__(self, store, smart_cast=True):
        self.store = store
        self.smart_cast = smart_cast

    def __call__(self, var, cast=None, default=NOTSET, parse_default=False):
        return self.get_value(var, cast=cast, default=default, parse_default=parse_default)

    def __contains__(self, var):
        return var in self.store

    def str(self, var, default=NOTSET, multiline=False):
        """
        :rtype: str
        """
        value = self.get_value(var, cast=str, default=default)
        if multiline:
            return value.replace('\\n', '\n')
        return value

    def unicode(self, var, default=NOTSET):
        """Helper for python2
        :rtype: unicode
        """
        return self.get_value(var, cast=str, default=default)

    def bytes(self, var, default=NOTSET, encoding='utf8'):
        """
        :rtype: bytes
        """
        return self.get_value(var, cast=str).encode(encoding)

    def bool(self, var, default=NOTSET):
        """
        :rtype: bool
        """
        return self.get_value(var, cast=bool, default=default)

    def int(self, var, default=NOTSET):
        """
        :rtype: int
        """
        return self.get_value(var, cast=int, default=default)

    def float(self, var, default=NOTSET):
        """
        :rtype: float
        """
        return self.get_value(var, cast=float, default=default)

    def json(self, var, default=NOTSET):
        """
        :returns: Json parsed
        """
        return self.get_value(var, cast=json.loads, default=default)

    def list(self, var, cast=None, default=NOTSET):
        """
        :rtype: list
        """
        return self.get_value(var, cast=list if not cast else [cast], default=default)

    def tuple(self, var, cast=None, default=NOTSET):
        """
        :rtype: tuple
        """
        return self.get_value(var, cast=tuple if not cast else (cast,), default=default)

    def dict(self, var, cast=dict, default=NOTSET):
        """
        :rtype: dict
        """
        return self.get_value(var, cast=cast, default=default)

    def url(self, var, default=NOTSET):
        """
        :rtype: urlparse.ParseResult
        """
        return self.get_value(var, cast=urllib.parse.urlparse, default=default, parse_default=True)

    def get_value(self, var, cast=None, default=NOTSET, parse_default=False):
        """Return value for given environment variable.
        :param var: Name of variable.
        :param cast: Type to cast return value as.
        :param default: If var not present in environ, return this instead.
        :param parse_default: force to parse default..
        :returns: Value from environment or default (if set)
        """

        # if var in self.scheme:
        #     var_info = self.scheme[var]
        #
        #     try:
        #         has_default = len(var_info) == 2
        #     except TypeError:
        #         has_default = False
        #
        #     if has_default:
        #         if not cast:
        #             cast = var_info[0]
        #
        #         if default is self.NOTSET:
        #             try:
        #                 default = var_info[1]
        #             except IndexError:
        #                 pass
        #     else:
        #         if not cast:
        #             cast = var_info

        try:
            value = self.store[var]
        except KeyError:
            if default is self.NOTSET:
                error_msg = "Set the %s environment variable" % var
                raise ImproperlyConfigured(error_msg)

            value = default

        # Resolve any proxied values
        if hasattr(value, 'startswith') and value.startswith('$'):
            value = value.lstrip('$')
            value = self.get_value(value, cast=cast, default=default)

        # Smart casting
        if self.smart_cast:
            if cast is None and default is not None and not (default is self.NOTSET):
                cast = type(default)

        if value != default or (parse_default and value):
            value = self.parse_value(value, cast)

        return value

    @classmethod
    def parse_value(cls, value, cast):
        """Parse and cast provided value
        :param value: Stringed value.
        :param cast: Type to cast return value as.
        :returns: Casted value
        """
        if cast is None:
            return value
        elif cast is bool:
            try:
                value = int(value) != 0
            except ValueError:
                value = value.lower() in cls.BOOLEAN_TRUE_STRINGS
        elif isinstance(cast, list):
            value = list(map(cast[0], [x for x in value.split(',') if x]))
        elif isinstance(cast, tuple):
            val = value.strip('(').strip(')').split(',')
            value = tuple(map(cast[0], [x for x in val if x]))
        elif isinstance(cast, dict):
            key_cast = cast.get('key', str)
            value_cast = cast.get('value', str)
            value_cast_by_key = cast.get('cast', dict())
            value = dict(map(
                lambda kv: (
                    key_cast(kv[0]),
                    cls.parse_value(kv[1], value_cast_by_key.get(kv[0], value_cast))
                ),
                [val.split('=') for val in value.split(';') if val]
            ))
        elif cast is dict:
            value = dict([val.split('=') for val in value.split(',') if val])
        elif cast is list:
            value = [x for x in value.split(',') if x]
        elif cast is tuple:
            val = value.strip('(').strip(')').split(',')
            value = tuple([x for x in val if x])
        elif cast is float:
            # clean string
            float_str = re.sub(r'[^\d,\.]', '', value)
            # split for avoid thousand separator and different locale comma/dot symbol
            parts = re.split(r'[,\.]', float_str)
            if len(parts) == 1:
                float_str = parts[0]
            else:
                float_str = "{0}.{1}".format(''.join(parts[0:-1]), parts[-1])
            value = float(float_str)
        else:
            value = cast(value)
        return value

    def db_url(self, var, default=NOTSET, engine=None):
        """Returns a config dictionary, defaulting to DATABASE_URL.
        :rtype: dict
        """
        return self.db_url_config(self.get_value(var, default=default), engine=engine)
    db = db_url

    def cache_url(self, var, default=NOTSET, backend=None):
        """Returns a config dictionary, defaulting to CACHE_URL.
        :rtype: dict
        """
        return self.cache_url_config(self.url(var, default=default), backend=backend)
    cache = cache_url

    def email_url(self, var, default=NOTSET, backend=None):
        """Returns a config dictionary, defaulting to EMAIL_URL.
        :rtype: dict
        """
        return self.email_url_config(self.url(var, default=default), backend=backend)
    email = email_url

    def path(self, var, default=NOTSET, **kwargs):
        """
        :rtype: Path
        """
        return self.PATH_CLASS(self.get_value(var, default=default), **kwargs)

    @classmethod
    def cache_url_config(cls, url, backend=None):
        """Pulled from DJ-Cache-URL, parse an arbitrary Cache URL.
        :param url:
        :param backend:
        :return:
        """
        if not isinstance(url, cls.URL_CLASS):
            if not url:
                return {}
            else:
                url = urllib.parse.urlparse(url)

        if url.scheme not in cls.CACHE_SCHEMES and backend is None:
            raise ImproperlyConfigured('Invalid cache schema {}'.format(url.scheme))

        location = url.netloc.split(',')
        if len(location) == 1:
            location = location[0]

        config = {
            'BACKEND': backend if backend else cls.CACHE_SCHEMES[url.scheme],
            'LOCATION': location,
        }

        # Add the drive to LOCATION
        if url.scheme == 'filecache':
            config.update({
                'LOCATION': url.netloc + url.path,
            })

        if url.path and url.scheme in ['memcache', 'pymemcache']:
            config.update({
                'LOCATION': 'unix:' + url.path,
            })
        elif url.scheme.startswith('redis'):
            if url.hostname:
                scheme = url.scheme.replace('cache', '')
            else:
                scheme = 'unix'
            locations = [scheme + '://' + loc + url.path for loc in url.netloc.split(',')]
            config['LOCATION'] = locations[0] if len(locations) == 1 else locations

        if url.query:
            config_options = {}
            for k, v in urllib.parse.parse_qs(url.query).items():
                opt = {k.upper(): _cast(v[0])}
                if k.upper() in cls._CACHE_BASE_OPTIONS:
                    config.update(opt)
                else:
                    config_options.update(opt)
            config['OPTIONS'] = config_options


        return config

    @classmethod
    def db_url_config(cls, url, engine=None):
        """Pulled from DJ-Database-URL, parse an arbitrary Database URL.
        Support currently exists for PostgreSQL, PostGIS, MySQL, Oracle and SQLite.
        SQLite connects to file based databases. The same URL format is used, omitting the hostname,
        and using the "file" portion as the filename of the database.
        This has the effect of four slashes being present for an absolute file path:
        >>> from environ import Env
        >>> Env.db_url_config('sqlite:////full/path/to/your/file.sqlite')
        {'ENGINE': 'django.db.backends.sqlite3', 'HOST': '', 'NAME': '/full/path/to/your/file.sqlite', 'PASSWORD': '', 'PORT': '', 'USER': ''}
        >>> Env.db_url_config('postgres://uf07k1i6d8ia0v:wegauwhgeuioweg@ec2-107-21-253-135.compute-1.amazonaws.com:5431/d8r82722r2kuvn')
        {'ENGINE': 'django.db.backends.postgresql', 'HOST': 'ec2-107-21-253-135.compute-1.amazonaws.com', 'NAME': 'd8r82722r2kuvn', 'PASSWORD': 'wegauwhgeuioweg', 'PORT': 5431, 'USER': 'uf07k1i6d8ia0v'}
        """
        if not isinstance(url, cls.URL_CLASS):
            if url == 'sqlite://:memory:':
                # this is a special case, because if we pass this URL into
                # urlparse, urlparse will choke trying to interpret "memory"
                # as a port number
                return {
                    'ENGINE': cls.DB_SCHEMES['sqlite'],
                    'NAME': ':memory:'
                }
                # note: no other settings are required for sqlite
            url = urllib.parse.urlparse(url)

        config = {}

        # Remove query strings.
        path = url.path[1:]
        path = urllib.parse.unquote_plus(path.split('?', 2)[0])

        if url.scheme == 'sqlite':
            if path == '':
                # if we are using sqlite and we have no path, then assume we
                # want an in-memory database (this is the behaviour of  sqlalchemy)
                path = ':memory:'
            if url.netloc:
                warnings.warn(
                    'SQLite URL contains host component %r, it will be ignored' % url.netloc, stacklevel=3)
        if url.scheme == 'ldap':
            path = '{scheme}://{hostname}'.format(scheme=url.scheme, hostname=url.hostname)
            if url.port:
                path += ':{port}'.format(port=url.port)

        # Update with environment configuration.
        config.update({
            'NAME': path or '',
            'USER': _cast_urlstr(url.username) or '',
            'PASSWORD': _cast_urlstr(url.password) or '',
            'HOST': url.hostname or '',
            'PORT': _cast_int(url.port) or '',
        })

        if url.scheme == 'postgres' and path.startswith('/'):
            config['HOST'], config['NAME'] = path.rsplit('/', 1)

        if url.scheme == 'oracle' and path == '':
            config['NAME'] = config['HOST']
            config['HOST'] = ''

        if url.scheme == 'oracle':
            # Django oracle/base.py strips port and fails on non-string value
            if not config['PORT']:
                del(config['PORT'])
            else:
                config['PORT'] = str(config['PORT'])

        if url.query:
            config_options = {}
            for k, v in urllib.parse.parse_qs(url.query).items():
                if k.upper() in cls._DB_BASE_OPTIONS:
                    config.update({k.upper(): _cast(v[0])})
                else:
                    config_options.update({k: _cast_int(v[0])})
            config['OPTIONS'] = config_options

        if engine:
            config['ENGINE'] = engine
        else:
            config['ENGINE'] = url.scheme

        if config['ENGINE'] in cls.DB_SCHEMES:
            config['ENGINE'] = cls.DB_SCHEMES[config['ENGINE']]

        if not config.get('ENGINE', False):
            warnings.warn("Engine not recognized from url: {0}".format(config))
            return {}

        return config

    @classmethod
    def email_url_config(cls, url, backend=None):
        """Parses an email URL."""

        config = {}

        url = urllib.parse.urlparse(url) if not isinstance(url, cls.URL_CLASS) else url

        # Remove query strings
        path = url.path[1:]
        path = urllib.parse.unquote_plus(path.split('?', 2)[0])

        # Update with environment configuration
        config.update({
            'EMAIL_FILE_PATH': path,
            'EMAIL_HOST_USER': _cast_urlstr(url.username),
            'EMAIL_HOST_PASSWORD': _cast_urlstr(url.password),
            'EMAIL_HOST': url.hostname,
            'EMAIL_PORT': _cast_int(url.port),
        })

        if backend:
            config['EMAIL_BACKEND'] = backend
        elif url.scheme not in cls.EMAIL_SCHEMES:
            raise ImproperlyConfigured('Invalid email schema %s' % url.scheme)
        elif url.scheme in cls.EMAIL_SCHEMES:
            config['EMAIL_BACKEND'] = cls.EMAIL_SCHEMES[url.scheme]

        if url.scheme in ('smtps', 'smtp+tls'):
            config['EMAIL_USE_TLS'] = True
        elif url.scheme == 'smtp+ssl':
            config['EMAIL_USE_SSL'] = True

        if url.query:
            config_options = {}
            for k, v in urllib.parse.parse_qs(url.query).items():
                opt = {k.upper(): _cast_int(v[0])}
                if k.upper() in cls._EMAIL_BASE_OPTIONS:
                    config.update(opt)
                else:
                    config_options.update(opt)
            config['OPTIONS'] = config_options

        return config

    # @classmethod
    # def add_type(cls, name, function):
    #     cls[name] = function
    #
    # @classmethod
    # def add_db_type(cls, name, backend):
    #     cls.DB_SCHEMES[name] = backend
    #
    # @classmethod
    # def add_cache_type(cls, name, backend):
    #     cls.CACHE_SCHEMES[name] = backend
    #
    # @classmethod
    # def add_email_type(cls, name, backend):
    #     cls.EMAIL_SCHEMES[name] = backend


class EnvLoader(BaseLoader):

    def __init__(self, env_file=None, smart_cast=True):
        self.smart_cast = smart_cast
        if env_file:
            self.store = self.read_env(env_file)
        else:
            self.store = environ

    @staticmethod
    def read_env(env_file):
        """Read a .env file into os.environ.
        If not given a path to a dotenv path, does filthy magic stack backtracking
        to find manage.py and then find the dotenv.
        http://www.wellfireinteractive.com/blog/easier-12-factor-django/
        https://gist.github.com/bennylope/2999704
        """

        with open(env_file) if isinstance(env_file, basestring) else env_file as f:
            env_data = {}
            for line in f:
                m1 = re.match(r'\A(?:export )?([A-Za-z_0-9]+)=(.*)\Z', line)
                if m1:
                    key, val = m1.group(1), m1.group(2)
                    m2 = re.match(r"\A'(.*)'\Z", val)
                    if m2:
                        val = m2.group(1)
                    m3 = re.match(r'\A"(.*)"\Z', val)
                    if m3:
                        val = re.sub(r'\\(.)', r'\1', m3.group(1))
                    env_data[key] = str(val)
