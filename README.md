# tgTransloader
transload, manage files, and more from telegram bot

#fix for thumb-gen
```
sed -i 's/from cv2        import cv2/import cv2/' $(pip show moviepy | grep Location | awk -F": " '{print $2 "/thumb_gen/application.py"}')
sed -i 's#font\.getsize(\(.*\))\[0\]#font.getbbox(\1)[2]-font.getbbox(\1)[0]#' $(pip show moviepy | grep Location | awk -F": " '{print $2 "/thumb_gen/application.py"}')
sed -i 's#font\.getsize(\(.*\))\[1\]#font.getbbox(\1)[3]-font.getbbox(\1)[1]#' $(pip show moviepy | grep Location | awk -F": " '{print $2 "/thumb_gen/application.py"}')
```
