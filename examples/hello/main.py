import os

if __name__ == '__main__':
    os.makedirs("output", exist_ok=True)
    with open('output/hello.txt', 'w') as f:
        f.write('Hello!')
