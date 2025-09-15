from time import sleep
import random
while True:
    try:
        with open("./test_log.txt", "a") as file:
            c = random.randint(1,10)
            if 1 < c < 7: 
                file.write("normal line")
            elif c == 8:
                file.write("[ERR] this line error")
            else:
                file.write("[WARN] pohui")
            file.write("\n")
            sleep(1)
    except KeyboardInterrupt:
        break
