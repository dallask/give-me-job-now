# Candidate photo (optional)

To show a headshot on PDFs that support it (`templates/cv/enhancv-inspired.html` and ReportLab layout):

1. Add an image here, e.g. `photo.jpg` (square-ish works best; it will be cropped to a circle in the HTML template).
2. Set in `config/candidate.yaml` at the top level:

   ```yaml
   photo: sources/candidate/photo.jpg
   ```

   You can instead use `contact.photo` if you prefer grouping with contact fields.

Supported formats: common raster formats (JPEG, PNG, WebP) readable by Pillow/ReportLab/WeasyPrint.
