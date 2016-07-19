# Overview

These are instructions for manual configuration of `/etc/nginx/sites-enabled/lms`.  Work is underway to handle this via Ansible.


* Configure the location that serves the SCORM content assets.  Within the main `server {` block, add

```
#uploaded scorm packages
location ~ ^/media/scorms/(?P<file>.*) {
    add_header 'Access-Control-Allow-Origin' '*';
    add_header 'Access-Control-Allow-Credentials' 'true';
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';

    root /edx/var/edxapp/media/scorms;
    try_files /$file =404;
    expires 31536000s;
}
```

You can choose to set a different value for 
    
    add_header 'Access-Control-Allow-Origin' '*';

to make a more restrictive CORS header; e.g,. 

    add_header 'Access-Control-Allow-Origin' '*.mydomain.com';

You can also choose a different path from the web root, if you like, but the default configuration will use `/media/scorms`.

* Within the main `server {` block, comment out this block, as the player code contain xml and json files.  _TODO: try making this more specific to the player code directory._

```
# return a 403 for static files that shouldn't be
# in the staticfiles directory
#location ~ ^/static/(?:.*)(?:\.xml|\.json|README.TXT) {
#    return 403;
#}
```

* Within the `location ~ ^/static//(?P<file>.*) {` block inside the main
`server {` block, add the following

```
    # scorm players
    location ~ "/scorm/(?P<file>.*)" {
      add_header 'Access-Control-Allow-Origin' '*';
      add_header 'Access-Control-Allow-Credentials' 'true';
      add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
      try_files /scormplayers/$file =404;
    }
```

As with the SCORM content assets block, you can choose to set a different value for the `Access-Control-` headers.

The directory value for `try_files /scormplayers/...` can be changed to match the `location` key for the desired player code, inside the `EDXAPP_XBLOCK_SETTINGS` key of your `server-vars.yml` file.  As shown in the example from `README.md` in this repository,

```
EDXAPP_XBLOCK_SETTINGS:
  "ScormXBlock": {
    "SCORM_PLAYER_BACKENDS": {
      "ssla": {
        "name": "SSLA",
        "location": "/static/scorm/ssla/player.htm",
        "configuration": {}
      }
    },
    "SCORM_PKG_STORAGE_DIR": "scorms",
  }
```

the `"location"` key's value `/static/scorm`... should match the nginx location.  

* Reload the new configuration for Nginx

```
sudo service nginx configtest
sudo service nginx reload
```





