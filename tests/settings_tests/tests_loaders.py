import os
import warnings
import sys
import json
import unittest
import urllib.parse
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

from django.conf import ENVIRONMENT_VARIABLE, LazySettings, Settings, settings, loaders
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.test import (
    SimpleTestCase, TestCase, TransactionTestCase, modify_settings,
    override_settings, signals,
)
from django.test.utils import requires_tz_support
from django.urls import clear_script_prefix, set_script_prefix


class BaseLoaderTestCase(SimpleTestCase):

    URL = 'http://www.google.com/'
    POSTGRES = 'postgres://uf07k1:wegauwhg@ec2-107-21-253-135.compute-1.amazonaws.com:5431/d8r82722'
    MYSQL = 'mysql://bea6eb0:69772142@us-cdbr-east.cleardb.com/heroku_97681?reconnect=true'
    MYSQLGIS = 'mysqlgis://user:password@127.0.0.1/some_database'
    SQLITE = 'sqlite:////full/path/to/your/database/file.sqlite'
    ORACLE_TNS = 'oracle://user:password@sid/'
    ORACLE = 'oracle://user:password@host:1521/sid'
    CUSTOM_BACKEND = 'custom.backend://user:password@example.com:5430/database'
    REDSHIFT = 'redshift://user:password@examplecluster.abc123xyz789.us-west-2.redshift.amazonaws.com:5439/dev'
    MEMCACHE = 'memcache://127.0.0.1:11211'
    REDIS = 'rediscache://127.0.0.1:6379/1?client_class=django_redis.client.DefaultClient&password=secret'
    EMAIL = 'smtps://user@domain.com:password@smtp.example.com:587'
    JSON = dict(one='bar', two=2, three=33.44)
    DICT = dict(foo='bar', test='on')
    PATH = '/home/dev'
    EXPORTED = 'exported var'

    @classmethod
    def generateData(cls):
        return {
            'STR_VAR': 'bar',
            'MULTILINE_STR_VAR': 'foo\\nbar',
            'INT_VAR': '42',
            'FLOAT_VAR': '33.3',
            'FLOAT_COMMA_VAR': '33,3',
            'FLOAT_STRANGE_VAR1': '123,420,333.3',
            'FLOAT_STRANGE_VAR2': '123.420.333,3',
            'BOOL_TRUE_VAR': '1',
            'BOOL_TRUE_VAR2': 'True',
            'BOOL_FALSE_VAR': '0',
            'BOOL_FALSE_VAR2': 'False',
            'PROXIED_VAR': '$STR_VAR',
            'INT_LIST': '42,33',
            'INT_TUPLE': '(42,33)',
            'STR_LIST_WITH_SPACES': ' foo,  bar',
            'EMPTY_LIST': '',
            'DICT_VAR': 'foo=bar,test=on',
            'DATABASE_URL': cls.POSTGRES,
            'DATABASE_MYSQL_URL': cls.MYSQL,
            'DATABASE_MYSQL_GIS_URL': cls.MYSQLGIS,
            'DATABASE_SQLITE_URL': cls.SQLITE,
            'DATABASE_ORACLE_URL': cls.ORACLE,
            'DATABASE_ORACLE_TNS_URL': cls.ORACLE_TNS,
            'DATABASE_REDSHIFT_URL': cls.REDSHIFT,
            'DATABASE_CUSTOM_BACKEND_URL': cls.CUSTOM_BACKEND,
            'CACHE_URL': cls.MEMCACHE,
            'CACHE_REDIS': cls.REDIS,
            'EMAIL_URL': cls.EMAIL,
            'URL_VAR': cls.URL,
            'JSON_VAR': json.dumps(cls.JSON),
            'PATH_VAR': cls.PATH,
            'EXPORTED_VAR': cls.EXPORTED
        }

    def assertTypeAndValue(self, type_, expected, actual):
        self.assertEqual(type_, type(actual))
        self.assertEqual(expected, actual)

    def setUp(self):
        self.loader = loaders.BaseLoader(self.generateData())

    def test_not_present_with_default(self):
        self.assertEqual(3, self.loader('not_present', default=3))

    def test_not_present_without_default(self):
        self.assertRaises(ImproperlyConfigured, self.loader, 'not_present')

    def test_contains(self):
        self.assertTrue('STR_VAR' in self.loader)
        self.assertTrue('EMPTY_LIST' in self.loader)
        self.assertFalse('I_AM_NOT_A_VAR' in self.loader)

    def test_str(self):
        self.assertTypeAndValue(str, 'bar', self.loader('STR_VAR'))
        self.assertTypeAndValue(str, 'bar', self.loader.str('STR_VAR'))
        self.assertTypeAndValue(str, 'foo\\nbar', self.loader.str('MULTILINE_STR_VAR'))
        self.assertTypeAndValue(str, 'foo\nbar', self.loader.str('MULTILINE_STR_VAR', multiline=True))

    def test_bytes(self):
        self.assertTypeAndValue(bytes, b'bar', self.loader.bytes('STR_VAR'))

    def test_int(self):
        self.assertTypeAndValue(int, 42, self.loader('INT_VAR', cast=int))
        self.assertTypeAndValue(int, 42, self.loader.int('INT_VAR'))

    def test_int_with_none_default(self):
        self.assertTrue(self.loader('NOT_PRESENT_VAR', cast=int, default=None) is None)

    def test_float(self):
        self.assertTypeAndValue(float, 33.3, self.loader('FLOAT_VAR', cast=float))
        self.assertTypeAndValue(float, 33.3, self.loader.float('FLOAT_VAR'))

        self.assertTypeAndValue(float, 33.3, self.loader('FLOAT_COMMA_VAR', cast=float))
        self.assertTypeAndValue(float, 123420333.3, self.loader('FLOAT_STRANGE_VAR1', cast=float))
        self.assertTypeAndValue(float, 123420333.3, self.loader('FLOAT_STRANGE_VAR2', cast=float))

    def test_bool_true(self):
        self.assertTypeAndValue(bool, True, self.loader('BOOL_TRUE_VAR', cast=bool))
        self.assertTypeAndValue(bool, True, self.loader('BOOL_TRUE_VAR2', cast=bool))
        self.assertTypeAndValue(bool, True, self.loader.bool('BOOL_TRUE_VAR'))

    def test_bool_false(self):
        self.assertTypeAndValue(bool, False, self.loader('BOOL_FALSE_VAR', cast=bool))
        self.assertTypeAndValue(bool, False, self.loader('BOOL_FALSE_VAR2', cast=bool))
        self.assertTypeAndValue(bool, False, self.loader.bool('BOOL_FALSE_VAR'))

    def test_proxied_value(self):
        self.assertEqual('bar', self.loader('PROXIED_VAR'))

    def test_int_list(self):
        self.assertTypeAndValue(list, [42, 33], self.loader('INT_LIST', cast=[int]))
        self.assertTypeAndValue(list, [42, 33], self.loader.list('INT_LIST', int))

    def test_int_tuple(self):
        self.assertTypeAndValue(tuple, (42, 33), self.loader('INT_LIST', cast=(int,)))
        self.assertTypeAndValue(tuple, (42, 33), self.loader.tuple('INT_LIST', int))
        self.assertTypeAndValue(tuple, ('42', '33'), self.loader.tuple('INT_LIST'))

    def test_str_list_with_spaces(self):
        self.assertTypeAndValue(list, [' foo', '  bar'],
                                self.loader('STR_LIST_WITH_SPACES', cast=[str]))
        self.assertTypeAndValue(list, [' foo', '  bar'],
                                self.loader.list('STR_LIST_WITH_SPACES'))

    def test_empty_list(self):
        self.assertTypeAndValue(list, [], self.loader('EMPTY_LIST', cast=[int]))

    def test_dict_value(self):
        self.assertTypeAndValue(dict, self.DICT, self.loader.dict('DICT_VAR'))

    def test_dict_parsing(self):
        self.assertEqual({'a': '1'}, self.loader.parse_value('a=1', dict))
        self.assertEqual({'a': 1}, self.loader.parse_value('a=1', dict(value=int)))
        self.assertEqual({'a': ['1', '2', '3']}, self.loader.parse_value('a=1,2,3', dict(value=[str])))
        self.assertEqual({'a': [1, 2, 3]}, self.loader.parse_value('a=1,2,3', dict(value=[int])))
        self.assertEqual({'a': 1, 'b': [1.1, 2.2], 'c': 3},
                         self.loader.parse_value('a=1;b=1.1,2.2;c=3', dict(value=int, cast=dict(b=[float]))))

        self.assertEqual({'a': "uname", 'c': "http://www.google.com", 'b': True},
                         self.loader.parse_value('a=uname;c=http://www.google.com;b=True', dict(value=str, cast=dict(b=bool))))

    def test_url_value(self):
        url = self.loader.url('URL_VAR')
        self.assertEqual(url.__class__, self.loader.URL_CLASS)
        self.assertEqual(url.geturl(), self.URL)
        self.assertEqual(None, self.loader.url('OTHER_URL', default=None))

    def test_url_encoded_parts(self):
        password_with_unquoted_characters = "#password"
        encoded_url = "mysql://user:%s@127.0.0.1:3306/dbname" % urllib.parse.quote(password_with_unquoted_characters)
        parsed_url = self.loader.db_url_config(encoded_url)
        self.assertEqual(parsed_url['PASSWORD'], password_with_unquoted_characters)

    def test_db_url_value(self):
        pg_config = self.loader.db('DATABASE_URL')
        self.assertEqual(pg_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(pg_config['NAME'], 'd8r82722')
        self.assertEqual(pg_config['HOST'], 'ec2-107-21-253-135.compute-1.amazonaws.com')
        self.assertEqual(pg_config['USER'], 'uf07k1')
        self.assertEqual(pg_config['PASSWORD'], 'wegauwhg')
        self.assertEqual(pg_config['PORT'], 5431)

        mysql_config = self.loader.db('DATABASE_MYSQL_URL')
        self.assertEqual(mysql_config['ENGINE'], 'django.db.backends.mysql')
        self.assertEqual(mysql_config['NAME'], 'heroku_97681')
        self.assertEqual(mysql_config['HOST'], 'us-cdbr-east.cleardb.com')
        self.assertEqual(mysql_config['USER'], 'bea6eb0')
        self.assertEqual(mysql_config['PASSWORD'], '69772142')
        self.assertEqual(mysql_config['PORT'], '')

        mysql_gis_config = self.loader.db('DATABASE_MYSQL_GIS_URL')
        self.assertEqual(mysql_gis_config['ENGINE'], 'django.contrib.gis.db.backends.mysql')
        self.assertEqual(mysql_gis_config['NAME'], 'some_database')
        self.assertEqual(mysql_gis_config['HOST'], '127.0.0.1')
        self.assertEqual(mysql_gis_config['USER'], 'user')
        self.assertEqual(mysql_gis_config['PASSWORD'], 'password')
        self.assertEqual(mysql_gis_config['PORT'], '')

        oracle_config = self.loader.db('DATABASE_ORACLE_TNS_URL')
        self.assertEqual(oracle_config['ENGINE'], 'django.db.backends.oracle')
        self.assertEqual(oracle_config['NAME'], 'sid')
        self.assertEqual(oracle_config['HOST'], '')
        self.assertEqual(oracle_config['USER'], 'user')
        self.assertEqual(oracle_config['PASSWORD'], 'password')
        self.assertFalse('PORT' in oracle_config)

        oracle_config = self.loader.db('DATABASE_ORACLE_URL')
        self.assertEqual(oracle_config['ENGINE'], 'django.db.backends.oracle')
        self.assertEqual(oracle_config['NAME'], 'sid')
        self.assertEqual(oracle_config['HOST'], 'host')
        self.assertEqual(oracle_config['USER'], 'user')
        self.assertEqual(oracle_config['PASSWORD'], 'password')
        self.assertEqual(oracle_config['PORT'], '1521')

        redshift_config = self.loader.db('DATABASE_REDSHIFT_URL', engine='django_redshift_backend')
        self.assertEqual(redshift_config['ENGINE'], 'django_redshift_backend')
        self.assertEqual(redshift_config['NAME'], 'dev')
        self.assertEqual(redshift_config['HOST'], 'examplecluster.abc123xyz789.us-west-2.redshift.amazonaws.com')
        self.assertEqual(redshift_config['USER'], 'user')
        self.assertEqual(redshift_config['PASSWORD'], 'password')
        self.assertEqual(redshift_config['PORT'], 5439)

        sqlite_config = self.loader.db('DATABASE_SQLITE_URL')
        self.assertEqual(sqlite_config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(sqlite_config['NAME'], '/full/path/to/your/database/file.sqlite')

        custom_backend_config = self.loader.db('DATABASE_CUSTOM_BACKEND_URL')
        self.assertEqual(custom_backend_config['ENGINE'], 'custom.backend')
        self.assertEqual(custom_backend_config['NAME'], 'database')
        self.assertEqual(custom_backend_config['HOST'], 'example.com')
        self.assertEqual(custom_backend_config['USER'], 'user')
        self.assertEqual(custom_backend_config['PASSWORD'], 'password')
        self.assertEqual(custom_backend_config['PORT'], 5430)

    def test_cache_url_value(self):
        cache_config = self.loader.cache_url('CACHE_URL')
        self.assertEqual(cache_config['BACKEND'], 'django.core.cache.backends.memcached.MemcachedCache')
        self.assertEqual(cache_config['LOCATION'], '127.0.0.1:11211')

    def test_email_url_value(self):
        email_config = self.loader.email_url('EMAIL_URL')
        self.assertEqual(email_config['EMAIL_BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')
        self.assertEqual(email_config['EMAIL_HOST'], 'smtp.example.com')
        self.assertEqual(email_config['EMAIL_HOST_PASSWORD'], 'password')
        self.assertEqual(email_config['EMAIL_HOST_USER'], 'user@domain.com')
        self.assertEqual(email_config['EMAIL_PORT'], 587)
        self.assertEqual(email_config['EMAIL_USE_TLS'], True)

    def test_json_value(self):
        self.assertEqual(self.JSON, self.loader.json('JSON_VAR'))

    def test_path(self):
        root = self.loader.path('PATH_VAR')
        self.assertEqual(Path(self.PATH), root)

    def test_smart_cast(self):
        self.assertEqual(self.loader.get_value('STR_VAR', default='string'), 'bar')
        self.assertEqual(self.loader.get_value('BOOL_TRUE_VAR', default=True), True)
        self.assertEqual(self.loader.get_value('BOOL_FALSE_VAR', default=True), False)
        self.assertEqual(self.loader.get_value('INT_VAR', default=1), 42)
        self.assertEqual(self.loader.get_value('FLOAT_VAR', default=1.2), 33.3)

    def test_exported(self):
        self.assertEqual(self.EXPORTED, self.loader('EXPORTED_VAR'))


class DatabaseBaseLoaderTestCase(SimpleTestCase):

    def test_postgres_parsing(self):
        url = 'postgres://uf07k1i6d8ia0v:wegauwhgeuioweg@ec2-107-21-253-135.compute-1.amazonaws.com:5431/d8r82722r2kuvn'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(url['NAME'], 'd8r82722r2kuvn')
        self.assertEqual(url['HOST'], 'ec2-107-21-253-135.compute-1.amazonaws.com')
        self.assertEqual(url['USER'], 'uf07k1i6d8ia0v')
        self.assertEqual(url['PASSWORD'], 'wegauwhgeuioweg')
        self.assertEqual(url['PORT'], 5431)

    def test_postgres_parsing_unix_domain_socket(self):
        url = 'postgres:////var/run/postgresql/db'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(url['NAME'], 'db')
        self.assertEqual(url['HOST'], '/var/run/postgresql')

    def test_postgis_parsing(self):
        url = 'postgis://uf07k1i6d8ia0v:wegauwhgeuioweg@ec2-107-21-253-135.compute-1.amazonaws.com:5431/d8r82722r2kuvn'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.contrib.gis.db.backends.postgis')
        self.assertEqual(url['NAME'], 'd8r82722r2kuvn')
        self.assertEqual(url['HOST'], 'ec2-107-21-253-135.compute-1.amazonaws.com')
        self.assertEqual(url['USER'], 'uf07k1i6d8ia0v')
        self.assertEqual(url['PASSWORD'], 'wegauwhgeuioweg')
        self.assertEqual(url['PORT'], 5431)

    def test_mysql_gis_parsing(self):
        url = 'mysqlgis://uf07k1i6d8ia0v:wegauwhgeuioweg@ec2-107-21-253-135.compute-1.amazonaws.com:5431/d8r82722r2kuvn'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.contrib.gis.db.backends.mysql')
        self.assertEqual(url['NAME'], 'd8r82722r2kuvn')
        self.assertEqual(url['HOST'], 'ec2-107-21-253-135.compute-1.amazonaws.com')
        self.assertEqual(url['USER'], 'uf07k1i6d8ia0v')
        self.assertEqual(url['PASSWORD'], 'wegauwhgeuioweg')
        self.assertEqual(url['PORT'], 5431)

    def test_cleardb_parsing(self):
        url = 'mysql://bea6eb025ca0d8:69772142@us-cdbr-east.cleardb.com/heroku_97681db3eff7580?reconnect=true'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.db.backends.mysql')
        self.assertEqual(url['NAME'], 'heroku_97681db3eff7580')
        self.assertEqual(url['HOST'], 'us-cdbr-east.cleardb.com')
        self.assertEqual(url['USER'], 'bea6eb025ca0d8')
        self.assertEqual(url['PASSWORD'], '69772142')
        self.assertEqual(url['PORT'], '')

    def test_mysql_no_password(self):
        url = 'mysql://travis@localhost/test_db'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.db.backends.mysql')
        self.assertEqual(url['NAME'], 'test_db')
        self.assertEqual(url['HOST'], 'localhost')
        self.assertEqual(url['USER'], 'travis')
        self.assertEqual(url['PASSWORD'], '')
        self.assertEqual(url['PORT'], '')

    def test_empty_sqlite_url(self):
        url = 'sqlite://'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(url['NAME'], ':memory:')

    def test_memory_sqlite_url(self):
        url = 'sqlite://:memory:'
        url = loaders.BaseLoader.db_url_config(url)

        self.assertEqual(url['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(url['NAME'], ':memory:')

    def test_memory_sqlite_url_warns_about_netloc(self):
        url = 'sqlite://missing-slash-path'
        with warnings.catch_warnings(record=True) as w:
            url = loaders.BaseLoader.db_url_config(url)
            self.assertEqual(url['ENGINE'], 'django.db.backends.sqlite3')
            self.assertEqual(url['NAME'], ':memory:')
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, UserWarning))

    def test_database_options_parsing(self):
        url = 'postgres://user:pass@host:1234/dbname?conn_max_age=600'
        url = loaders.BaseLoader.db_url_config(url)
        self.assertEqual(url['CONN_MAX_AGE'], 600)

        url = 'postgres://user:pass@host:1234/dbname?conn_max_age=None&autocommit=True&atomic_requests=False'
        url = loaders.BaseLoader.db_url_config(url)
        self.assertEqual(url['CONN_MAX_AGE'], None)
        self.assertEqual(url['AUTOCOMMIT'], True)
        self.assertEqual(url['ATOMIC_REQUESTS'], False)

        url = 'mysql://user:pass@host:1234/dbname?init_command=SET storage_engine=INNODB'
        url = loaders.BaseLoader.db_url_config(url)
        self.assertEqual(url['OPTIONS'], {
            'init_command': 'SET storage_engine=INNODB',
        })

    def test_database_ldap_url(self):
        url = 'ldap://cn=admin,dc=nodomain,dc=org:some_secret_password@ldap.nodomain.org/'
        url = loaders.BaseLoader.db_url_config(url, engine='ldapdb.backends.ldap')

        self.assertEqual(url['ENGINE'], 'ldapdb.backends.ldap')
        self.assertEqual(url['HOST'], 'ldap.nodomain.org')
        self.assertEqual(url['PORT'], '')
        self.assertEqual(url['NAME'], 'ldap://ldap.nodomain.org')
        self.assertEqual(url['USER'], 'cn=admin,dc=nodomain,dc=org')
        self.assertEqual(url['PASSWORD'], 'some_secret_password')


class CacheBaseLoaderTestCase(SimpleTestCase):

    def test_base_options_parsing(self):
        url = 'memcache://127.0.0.1:11211/?timeout=0&key_prefix=cache_&key_function=foo.get_key&version=1'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['KEY_PREFIX'], 'cache_')
        self.assertEqual(url['KEY_FUNCTION'], 'foo.get_key')
        self.assertEqual(url['TIMEOUT'], 0)
        self.assertEqual(url['VERSION'], 1)

        url = 'redis://127.0.0.1:6379/?timeout=None'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')

        self.assertEqual(url['TIMEOUT'], None)

    def test_memcache_parsing(self):
        url = 'memcache://127.0.0.1:11211'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.memcached.MemcachedCache')
        self.assertEqual(url['LOCATION'], '127.0.0.1:11211')

    def test_memcache_pylib_parsing(self):
        url = 'pymemcache://127.0.0.1:11211'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.memcached.PyLibMCCache')
        self.assertEqual(url['LOCATION'], '127.0.0.1:11211')

    def test_memcache_multiple_parsing(self):
        url = 'memcache://172.19.26.240:11211,172.19.26.242:11212'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.memcached.MemcachedCache')
        self.assertEqual(url['LOCATION'], ['172.19.26.240:11211', '172.19.26.242:11212'])

    def test_memcache_socket_parsing(self):
        url = 'memcache:///tmp/memcached.sock'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.memcached.MemcachedCache')
        self.assertEqual(url['LOCATION'], 'unix:/tmp/memcached.sock')

    def test_dbcache_parsing(self):
        url = 'dbcache://my_cache_table'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.db.DatabaseCache')
        self.assertEqual(url['LOCATION'], 'my_cache_table')

    def test_filecache_parsing(self):
        url = 'filecache:///var/tmp/django_cache'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.filebased.FileBasedCache')
        self.assertEqual(url['LOCATION'], '/var/tmp/django_cache')

    def test_filecache_windows_parsing(self):
        url = 'filecache://C:/foo/bar'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.filebased.FileBasedCache')
        self.assertEqual(url['LOCATION'], 'C:/foo/bar')

    def test_locmem_parsing(self):
        url = 'locmemcache://'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.locmem.LocMemCache')
        self.assertEqual(url['LOCATION'], '')

    def test_locmem_named_parsing(self):
        url = 'locmemcache://unique-snowflake'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.locmem.LocMemCache')
        self.assertEqual(url['LOCATION'], 'unique-snowflake')

    def test_dummycache_parsing(self):
        url = 'dummycache://'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.dummy.DummyCache')
        self.assertEqual(url['LOCATION'], '')

    def test_redis_parsing(self):
        url = 'rediscache://127.0.0.1:6379/1?client_class=django_redis.client.DefaultClient&password=secret'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')

        self.assertEqual(url['BACKEND'], 'django_redis.cache.RedisCache')
        self.assertEqual(url['LOCATION'], 'redis://127.0.0.1:6379/1')
        self.assertEqual(url['OPTIONS'], {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'PASSWORD': 'secret',
        })

    def test_redis_socket_parsing(self):
        url = 'rediscache:///path/to/socket:1'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')
        self.assertEqual(url['BACKEND'], 'django_redis.cache.RedisCache')
        self.assertEqual(url['LOCATION'], 'unix:///path/to/socket:1')

    def test_redis_with_password_parsing(self):
        url = 'rediscache://:redispass@127.0.0.1:6379/0'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')
        self.assertEqual('django_redis.cache.RedisCache', url['BACKEND'])
        self.assertEqual(url['LOCATION'], 'redis://:redispass@127.0.0.1:6379/0')

    def test_redis_multi_location_parsing(self):
        url = 'rediscache://host1:6379,host2:6379,host3:9999/1'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')

        self.assertEqual(url['BACKEND'], 'django_redis.cache.RedisCache')
        self.assertEqual(url['LOCATION'], [
            'redis://host1:6379/1',
            'redis://host2:6379/1',
            'redis://host3:9999/1',
        ])

    def test_redis_socket_url(self):
        url = 'redis://:redispass@/path/to/socket.sock?db=0'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')
        self.assertEqual('django_redis.cache.RedisCache', url['BACKEND'])
        self.assertEqual(url['LOCATION'], 'unix://:redispass@/path/to/socket.sock')
        self.assertEqual(url['OPTIONS'], {
            'DB': 0
        })

    def test_rediss_parsing(self):
        url = 'rediss://127.0.0.1:6379/1'
        url = loaders.BaseLoader.cache_url_config(url, backend='django_redis.cache.RedisCache')

        self.assertEqual(url['BACKEND'], 'django_redis.cache.RedisCache')
        self.assertEqual(url['LOCATION'], 'rediss://127.0.0.1:6379/1')

    def test_options_parsing(self):
        url = 'filecache:///var/tmp/django_cache?timeout=60&max_entries=1000&cull_frequency=0'
        url = loaders.BaseLoader.cache_url_config(url)

        self.assertEqual(url['BACKEND'], 'django.core.cache.backends.filebased.FileBasedCache')
        self.assertEqual(url['LOCATION'], '/var/tmp/django_cache')
        self.assertEqual(url['TIMEOUT'], 60)
        self.assertEqual(url['OPTIONS'], {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 0,
        })

    def test_custom_backend(self):
        url = 'memcache://127.0.0.1:5400?foo=option&bars=9001'
        backend = 'django_redis.cache.RedisCache'
        url = loaders.BaseLoader.cache_url_config(url, backend)

        self.assertEqual(url['BACKEND'], backend)
        self.assertEqual(url['LOCATION'], '127.0.0.1:5400')
        self.assertEqual(url['OPTIONS'], {
            'FOO': 'option',
            'BARS': 9001,
        })

    def test_unknown_backend(self):
        url = 'unknown-scheme://127.0.0.1:1000'
        with self.assertRaises(ImproperlyConfigured) as cm:
            loaders.BaseLoader.cache_url_config(url)
        self.assertEqual(str(cm.exception),
                         'Invalid cache schema unknown-scheme')

    def test_empty_url_is_mapped_to_empty_config(self):
        self.assertEqual(loaders.BaseLoader.cache_url_config(''), {})
        self.assertEqual(loaders.BaseLoader.cache_url_config(None), {})


class EmailBaseLoaderTestCase(SimpleTestCase):

    def test_smtp_parsing(self):
        url = 'smtps://user@domain.com:password@smtp.example.com:587'
        url = loaders.BaseLoader.email_url_config(url)

        self.assertEqual(url['EMAIL_BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')
        self.assertEqual(url['EMAIL_HOST'], 'smtp.example.com')
        self.assertEqual(url['EMAIL_HOST_PASSWORD'], 'password')
        self.assertEqual(url['EMAIL_HOST_USER'], 'user@domain.com')
        self.assertEqual(url['EMAIL_PORT'], 587)
        self.assertEqual(url['EMAIL_USE_TLS'], True)
