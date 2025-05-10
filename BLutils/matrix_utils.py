from mathutils import Matrix

def y_up_to_z_up_matrix():
    return Matrix.Rotation(-3.14159265 / 2, 4, 'X')

def convert_matrix(raw):
    m = Matrix(((raw[0], raw[4], raw[8], raw[12]),
                (raw[1], raw[5], raw[9], raw[13]),
                (raw[2], raw[6], raw[10], raw[14]),
                (raw[3], raw[7], raw[11], raw[15])))
    return m @ y_up_to_z_up_matrix()
