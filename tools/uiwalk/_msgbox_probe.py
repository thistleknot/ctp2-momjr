import sys
sys.path.insert(0,"/h/Program Files(x86)/Activision/Call To Power 2/Scenarios/mom/tools/uiwalk")
import cv2, numpy as np
import turnloop as T
f = cv2.imread(sys.argv[1])
print("shape", f.shape)
print("msg_box", T.find_msg_box(f))
print("msg_close", T.find_msg_close(f))
print("message_box_open", T.message_box_open(f))
b = T.find_msg_box(f)
if b:
    x0,y0,x1,y1 = b
    cv2.imwrite("msgcrop.png", f[max(0,y0-5):y0+70, max(0,x0-5):x1+10])
    print("crop saved", (x0,y0,x1,y1))
