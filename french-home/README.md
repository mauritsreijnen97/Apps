# The French Country Club

An original French country living magazine site with its own admin page for publishing articles and photos.
The name, tagline and about page can be changed in **Admin → Site settings**.

It needs no server or database. The public site reads everything from `content/site.json`.
The admin edits that file, uploads photos, and commits both to this GitHub repository in one go.
GitHub Pages then serves the updated site.

## Pages

| Page | What it is |
| --- | --- |
| `index.html` | The public site: home, journal by category, articles, gallery, about, photo credits |
| `admin.html` | The admin: write and edit articles, upload photos, change site settings, publish |

## Put the site online (once)

1. Merge this folder into the repository's default branch.
2. On GitHub, open the repository's **Settings → Pages** and choose **Deploy from a branch**, then the default branch and the `/ (root)` folder.
3. The site will then be at `https://<your-username>.github.io/<repository>/french-home/`,
   and the admin at `…/french-home/admin.html`. The footer of every page links to the admin.

## Sign in to the admin

The admin signs in with a GitHub **fine-grained personal access token** that may edit this repository only:

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. **Repository access:** Only select repositories → this repository
3. **Permissions → Repository permissions → Contents:** Read and write
4. Paste the token in the admin. Tick "Keep me signed in" only on your own devices.

The token is the only key to the admin. Anyone can open `admin.html`, but nobody can publish without a valid token.
The token is stored only in that browser and is sent only to `api.github.com`.
**Try it without publishing** opens the admin in preview mode, where you can explore without a token.

## Using the admin

- **Articles:** new article, title, subtitle, category, date, cover photo, story with formatting buttons, live preview. Untick *Published* to keep a draft hidden.
- **Photos:** upload or drag and drop. Photos are resized to 2000 px in the browser before upload. Captions, credits, and whether each appears in the gallery.
- **Site settings:** name, tagline, footer text, home page quote, about page, contact links and the categories in the menu.
- **Publish:** sends every change as a single commit. The live site updates within a minute or two.

Article formatting:

```
## Heading
### Smaller heading
**bold**  *italic*
> A quote
- list item
[link text](https://example.com)
![Photo caption](photos/uploads/my-photo.jpg)
```

## Run it locally

The site loads `content/site.json` with `fetch`, so it needs a web server rather than opening the file directly:

```
cd french-home
python3 -m http.server 8000
# open http://localhost:8000
```

## Starter photos

The starter photos come from Wikimedia Commons under CC0, CC BY and CC BY-SA licences. Each one is credited on the site's *Photo credits* page (`#/credits`).
Replace them with your own photos whenever you like.
