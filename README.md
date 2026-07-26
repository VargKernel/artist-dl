# artist-dl

A CLI utility for processing author post URLs from popular booru sites (reactor.cc, yande.re, konachan.com, e621.net, rule34.xxx).

It extracts authors from URLs, generates site-specific links, downloads pages with caching, and verifies availability.

## Features

* Accepts single or multiple URLs from CLI
* Supports input file (absolute or relative paths)
* Extracts URLs from text automatically
* Removes duplicate URLs while keeping order
* Detects supported booru sites automatically
* Extracts author names from URLs
* Generates equivalent links for multiple booru sites
* Uses local cache (`.cache`) to reduce requests
* Handles HTTP errors and network failures gracefully
* Treats some 403 responses as valid “empty results”
* Optional progress bar (`tqdm`)
* Writes output to file or stdout
* Groups results by site (`# site:` sections)
* Separates successful and failed results
* Real-time writing to output and log files
* Detailed logging (console + optional file)
* Uses persistent HTTP session for performance

## Supported Sites

1. reactor.cc  
2. yande.re  
3. e621.net  
4. rule34.xxx  
5. konachan.com  

## Installation

```bash
git clone <repository_url>
cd <repository_folder>
pip install -r requirements.txt
````

### Requirements

```
requests>=2.33.0
tqdm>=4.66.0 (optional)
```

## Usage

### Syntax

```bash
python3 artist-dl.py [OPTIONS] URL [URL...]
```

### Examples

```bash
python3 artist-dl.py https://reactor.cc/tag/artist
python3 artist-dl.py URL1 URL2 URL3...
python3 artist-dl.py -i input_urls.txt
python3 artist-dl.py -i input_urls.txt -o output_links.txt -f failed_links.txt -l run.log
```

## Options

* `-h`, `--help`
* `-v`, `--version`
* `-i`, `--input-file FILE` — input file with URLs
* `-o`, `--output-file FILE` — output file for results (optional, stdout if omitted)
* `-f`, `--failed-file FILE` — failed attempts log (optional)
* `-l`, `--log-file FILE` — execution log (optional)

## Files

* `input_urls.txt` — source URLs (one per line)
* `output_links.txt` — valid discovered links
* `failed_links.txt` — failed / not found results
* `run.log` — execution logs (optional)

## Output Behavior

| Mode     | Result          |
| -------- | --------------- |
| `-o` set | write to file   |
| omitted  | print to stdout |

## Cache

Pages are stored in `.cache/` using hashed filenames.

Cached results are reused automatically across runs.

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.
