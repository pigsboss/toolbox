# Toolbox

My homemade automation toolbox.

## CopyGeoTags
Copy GeoTags from reference photos.
### Syntax:
```bash
CopyGeoTags.py reference target [method]
```
reference - reference photo(s). Single file or directory.
target    - photo(s) that need GeoTags. Single file or directory.
method    - optional. Interpolation method, e.g., nearest, linear, cubic.

## pfetch

RSYNC with multi-threads parallelism and auto-retry.

### Examples:
```bash
$ python pfetch.py -azu user@server:/path fetch_list ./
```


## GeoTag

Get/Set geotags (GPS tags in EXIF) of photos. Requires piexif and PIL (pillow).

### Examples:

```bash
$ python GetGeoTags.py photo.jpg
$ python SetGeoTags.py 4.000000N 50.000000E 3.5 photo.jpg
```



## Check battery in CLI

Get Linux kernel reported battery percentage in command line interface.

### Example:

```bash
$ python battery_life.py
```

## Random password generator

Generates random password with specific length. Digits, lowercase letters and uppercase letters are included.

### Example:

The following command returns a random password with 8 characters.

```bash
$ python genpasswd.py 8
```

