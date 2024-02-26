# Building the WebSite

The website is hosted via GitHub Pages. 

  - The source files and code used to build the website are in `{project-root}/source`.
  - After building the website, the resulting files will appear in `{project-root}/docs` (or wherever the config.yaml file indicates).

## Setup

  1. Ensure that Python is installed, preferrably 3.10 or above.
  2. Install the required libraries:
```
    > cd {project-root}/source
    > pip install -r requirements.txt
```
  3. Verify that all configuration settings are as desired by inspecting file `{project-root}/source/config.yaml`. The settings are described in the python program, `build-website.py`.
  4. Clear the previous build (and answer 'y' at the prompt):
```
    > python build-website.py clean
```
  1. Rebuild the html, css and other files from source:
```
    > python build-website.py build
```
  1. Checkin the changes to github.
```
    > git add
    > git commit
    > git push
```
    (The above `git` commands may be different, to use the appropriate branch defined on GitHub for the website.)

## Preview the Website

To preview the website on your local computer:

```
  > cd {project-root}/build
  > python {project-root}/source/serve.py [PORT]
```

If you omit the port number, port 8000 will be used.

After the webserver is started, open a web browser and go to this url: http://localhost:{port}/index.html
