import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Union

import yaml

from dstack.server import __server_url__


class ConfigurationError(Exception):
    def __init__(self, message: str):
        self.message = message


class ProfileDoesNotExistError(ConfigurationError):
    def __init__(self, name: str):
        super().__init__(f"Profile '{name}' does not exist")
        self.name = name


class Profile(object):
    """To manage tokens CLI tools are used, so sensitive information like token and server is stored separately
    in configuration files. Every configuration file contains profiles section which stores all profiles the user
    have configured.

    Attributes:
         name: A name of the profile which can be used in code to identify token and server.
         token:  A token of selected profile.
         server: API endpoint.
         verify: Enable SSL certificate verification.
    """

    def __init__(self, name: str, token: Optional[str], server: str, verify: bool):
        """Create a profile object.

        Args:
            name: Profile name.
            token: A token which will be used with this profile.
            server: A server which provides API calls.
        """
        self.name = name
        self.token = token
        self.server = server
        self.verify = verify


class Config(ABC):
    """An abstract class for the configuration. It is needed to access and manage profiles.
    By default, system will use `YamlConfig` which works with YAML files located in working and home directories,
    but in some cases may be useful to store profiles in database or somewhere else. To do so one have to inherit this
    class and override certain methods in the proper way.
    """

    @abstractmethod
    def list_profiles(self) -> Dict[str, Profile]:
        """Return a map of profiles, where keys are profile names, values are `Profile` objects.

        Returns:
            A dictionary of available profiles. If there is no configured profiles empty dictionary will be returned.
        """
        pass

    @abstractmethod
    def get_profile(self, name: str) -> Optional[Profile]:
        """Get profile by name.

        Args:
            name (str): A name of profile you are looking for.

        Returns:
            A profile if it exists otherwise `None`.
        """
        pass

    @abstractmethod
    def add_or_replace_profile(self, profile: Profile):
        """Add or replace existing profile in the configuration. This operation doesn't persist anything, just changes.
        To persist configuration use `save` method.

        Args:
            profile (Profile): Profile to change. All data related to profile with same name will be replaced.
        """
        pass

    @abstractmethod
    def save(self):
        """Save configuration."""
        pass

    @abstractmethod
    def remove_profile(self, name: str) -> Profile:
        """Delete specified profile.

        Args:
            name (str): A name of the profile to delete.

        Returns:
            Deleted profile.
        """
        pass

    @abstractmethod
    def set_property(self, name: str, value: str):
        pass

    @abstractmethod
    def get_property(self, name: str) -> str:
        pass


class DictionaryBasedConfig(Config, ABC):
    @abstractmethod
    def get_dict(self):
        pass

    def set_property(self, name: str, value: str):
        data = self.get_dict()
        path = name.split(".")

        for p in path[:-1]:
            data[p] = data.get(p, {})
            data = data[p]

        data[path[-1]] = value

    def get_property(self, name: str) -> Optional[str]:
        data = self.get_dict()
        path = name.split(".")

        for p in path:
            data = data.get(p, None)
            if not data:
                return None

        # if the file was saved by Java library
        # values like 0.1 appeared without single quotes
        # so we have to force it to be a string
        return str(data)


class YamlConfig(DictionaryBasedConfig):
    """A class implements `Config` contracts for YAML format stored on disk. This implementation relies on PyYAML package.
    Comments can't be used in config file, because `save` method will remove it all. So, editing of configuration files
    is not recommended. To configure please use dstack CLI tools.

    See Also:
        `from_yaml_file`
    """

    def __init__(self, yaml_data, path: Path):
        """Create an instance from loaded data.

        Args:
            yaml_data: Dictionary like structure to store configuration.
            path: Filename on disk to save changes.
        """
        super().__init__()
        self.yaml_data = yaml_data
        self.path = path

    def list_profiles(self) -> Dict[str, Profile]:
        result = {}
        profiles = self.yaml_data.get("profiles", {})
        for k in profiles.keys():
            result[k] = self.get_profile(k)
        return result

    def get_profile(self, name: str) -> Optional[Profile]:
        """Return profile with specified name or `None`.

        Notes:
            In the case if server is not configured the standard endpoint will be used.

        Args:
            name (str): A name of profile.

        Returns:
            Profile if it exists, otherwise `None`.
        """
        profiles = self.yaml_data.get("profiles", {})
        profile = profiles.get(name, None)
        if profile is None:
            return None
        else:
            return Profile(name, profile.get("token", None),
                           profile.get("server", __server_url__), profile.get("verify", True))

    def add_or_replace_profile(self, profile: Profile):
        """Add or replaces existing profile.

        Notes:
            If server information refers to standard endpoint there will be no `server` key at all.
            Which coincides with `get_profile` behaviour.
        Args:
            profile: Profile to add or replace.
        """
        profiles = self.yaml_data.get("profiles", {})
        update = {}
        if profile.token:
            update["token"] = profile.token
        if profile.server != __server_url__:
            update["server"] = profile.server
        if not profile.verify:
            update["verify"] = profile.verify
        profiles[profile.name] = update
        self.yaml_data["profiles"] = profiles

    def save(self):
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True)
        content = yaml.dump(self.yaml_data)
        self.path.write_text(content, encoding="utf-8")

    def remove_profile(self, name: str) -> Profile:
        profiles = self.yaml_data.get("profiles", {})
        profile = profiles.get(name, None)

        if not profile:
            raise ProfileDoesNotExistError(name)

        del profiles[name]
        return profile

    def __repr__(self) -> str:
        return str(self.yaml_data)

    def get_dict(self):
        return self.yaml_data


class InPlaceConfig(DictionaryBasedConfig):
    def __init__(self):
        self.profiles = {}
        self.props = {}

    def list_profiles(self) -> Dict[str, Profile]:
        return self.profiles

    def get_profile(self, name: str) -> Optional[Profile]:
        return self.profiles.get(name, None)

    def add_or_replace_profile(self, profile: Profile):
        self.profiles[profile.name] = profile

    def save(self):
        pass

    def remove_profile(self, name: str) -> Profile:
        profile = self.profiles[name]
        del self.profiles[name]
        return profile

    def get_dict(self):
        return self.props


class ConfigFactory(ABC):
    @abstractmethod
    def get_config(self) -> Config:
        pass


class YamlConfigFactory(ConfigFactory):

    def get_config(self) -> Config:
        return from_yaml_file(_get_config_path(), error_if_not_exist=True)


def _get_config_path(path: Optional[str] = None) -> Path:
    config_path = Path.home() / ".dstack" / "config.yaml"
    env = os.getenv("DSTACK_CONFIG")
    env = Path(env) if env else None
    return path or env or config_path


def from_yaml_file(path: Path, error_if_not_exist: bool = False) -> Config:
    """Load YAML configuration.

    Args:
        path: Path to config file.
        error_if_not_exist: Force to produce error in the case of the file does not exist, by default it is `False`.
    Returns:
        YAML based configuration.

    Raises:
        ConfigurationException: If `error_if_not_exist` is `True` and file does not exist.
    """

    if not path.exists():
        if error_if_not_exist:
            raise ConfigurationError(f"Configuration file does not exist, type `dstack config` in command line")
        else:
            return YamlConfig({}, path)

    with path.open() as f:
        return YamlConfig(yaml.load(f, Loader=yaml.FullLoader), path)


__config_factory: ConfigFactory = YamlConfigFactory()


def configure(config: Union[Config, ConfigFactory]):
    global __config_factory
    if isinstance(config, Config):
        class SimpleConfigFactory(ConfigFactory):
            def get_config(self) -> Config:
                return config

        __config_factory = SimpleConfigFactory()
    elif isinstance(config, ConfigFactory):
        __config_factory = config
    else:
        raise TypeError(f"Config or ConfigFactory expected but found {type(config)}")


def get_config() -> Config:
    return __config_factory.get_config()
