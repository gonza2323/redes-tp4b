
def get_username():
    username = None
    while True:
        username = input("Ingrese su nombre de usuario: ")
        if not username:
            print("El nombre de usuario no puede estar vacío")
        elif ":" in username:
            print("El nombre de usuario no puede contener dos puntos ':'")
        else:
            break
    return username
