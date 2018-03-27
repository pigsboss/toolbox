# Toolbox

My homemade automation toolbox.

## CopyGeoTags
Copy GeoTags from reference photos.
### Syntax:
```bash
CopyGeoTags.py reference target [method]
```
`reference` is reference photo(s) (single file or directory), e.g., photos shot with your smartphone. `target`  is photo(s) that require GeoTags, e.g., photos shot with your DSLR. `method` indicates the interpolation method, e.g., nearest, linear, cubic, which is optional (Default: LINEAR).

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

