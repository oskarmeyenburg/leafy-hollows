# -*- coding: utf-8 -*-
from platform import system
import numpy
import math
import glob
import sys
import os

import scripts.world as world
import scripts.util as util

from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
from pygame.locals import *
import pygame


operating_system = system()


class Window:
    def __init__(self, caption):
        # Load options
        self.options = self.load_options()

        # Callbacks
        self.callback_quit = None

        # Init pygame
        pygame.init()

        # Explicitly use OpenGL 3.3 core (4.1 core also works)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK,
                                        pygame.GL_CONTEXT_PROFILE_CORE)
        #pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        #pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)

        # MacOS support
        if operating_system == "Darwin":
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, True)

        # Events
        self.keys: dict = dict.fromkeys([value for key, value in self.options.items() if key.startswith("key.")], 0) # 0 = Not pressed | 1 = Got pressed | 2 = Is pressed
        self.unicode: str = ""                  # Backspace = "\x08"
        self.mouse_buttons: [int] = [0, 0, 0]     # Left, Middle, Right | 0 = Not pressed | 1 = Got pressed | 2 = Is pressed
        self.mouse_pos: [int] = (0, 0, 0, 0)      # x, y, relx, rely
        self.mouse_wheel: [int] = [0, 0, 0, 0]    # x, y, relx, rely
        self.fps: int = 0
        self.delta_time: float = 1

        # Key functions
        if operating_system == "Darwin":
            self.mod_names = {
                pygame.__dict__[identifier]: identifier[4:].replace("_R", "Right ").replace("_L", "Left ").replace("_", "").replace("META", "Cmd").title()
                for index, identifier in enumerate(pygame.__dict__.keys())
                if identifier.startswith("KMOD_") and not identifier[5:] in ("NONE", "CTRL", "SHIFT", "ALT", "GUI", "META")
            }
        else:
            self.mod_names = {
                pygame.__dict__[identifier]: identifier[4:].replace("_R", "Right ").replace("_L", "Left ").replace("_", "").title()
                for index, identifier in enumerate(pygame.__dict__.keys())
                if identifier.startswith("KMOD_") and not identifier[5:] in ("NONE", "CTRL", "SHIFT", "ALT", "GUI", "META")
            }
        self.key_names = [pygame.__dict__[identifier] for identifier in pygame.__dict__.keys() if identifier.startswith("K_")]

        self.get_keys_all = pygame.key.get_pressed
        self.get_keys_all = pygame.key.get_mods
        self.get_key_name = pygame.key.name
        self.get_mod_name = lambda mod: self.mod_names[mod]

        # Window variables
        info = pygame.display.Info()
        self.screen_size = info.current_w, info.current_h
        self.width, self.height = self.size = self.pre_fullscreen = (int(info.current_w / 3 * 2), int(info.current_h / 5 * 3))
        self.fullscreen = False
        self.wireframe = False
        self.resize_supress = False
        self.stencil_rect = None
        
        # Window
        flags = DOUBLEBUF | RESIZABLE | OPENGL
        self.window = pygame.display.set_mode((self.width, self.height), flags=flags, vsync=self.options["enableVsync"])
        pygame.display.set_caption(caption)
        pygame.key.set_repeat(1000, 10)
        self.clock = pygame.time.Clock()
        self.camera: Camera = Camera(self)
        
        # OpenGL setup
        glViewport(0, 0, self.width, self.height)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        #glEnable(GL_MULTISAMPLE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Create vertex array object
        self.instance_vao = glGenVertexArrays(1)
        glBindVertexArray(self.instance_vao)

        # Create vertex buffer objects
        self.vertices_vbo, self.ebo, self.dest_vbo, self.source_or_color_vbo, self.shape_vbo = glGenBuffers(5)

        # Instanced shader inputs
        self.vbo_instances_length = 0
        self.vbo_instances_index = 0
        self.dest_vbo_data = numpy.zeros(0, dtype=numpy.float32)
        self.source_or_color_vbo_data = numpy.zeros(0, dtype=numpy.float32)
        self.shape_vbo_data = numpy.zeros(0, dtype=numpy.float32)

        # Vertices & texcoords
        vertices = numpy.array([
            -1.0, -1.0, 0.0, 0.0,  # bottom-left
            -1.0, 1.0, 0.0, 1.0,   # top-left
            1.0, 1.0, 1.0, 1.0,    # top-right
            1.0, -1.0, 1.0, 0.0    # bottom-right
        ], dtype=numpy.float32)

        glBindBuffer(GL_ARRAY_BUFFER, self.vertices_vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(2 * vertices.itemsize))
        
        # Create element buffer object (EBO) for indices
        indices = numpy.array([0, 1, 2, 0, 2, 3], dtype=numpy.uint32)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, len(indices) * 4, (GLuint * len(indices))(*indices), GL_STATIC_DRAW)

        # Create vertex buffer objects (VBOs) for draw data
        glEnableVertexAttribArray(2)
        glBindBuffer(GL_ARRAY_BUFFER, self.dest_vbo)
        glBufferData(GL_ARRAY_BUFFER, 0, self.dest_vbo_data, GL_DYNAMIC_DRAW)
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
        glVertexAttribDivisor(2, 1)

        glEnableVertexAttribArray(3)
        glBindBuffer(GL_ARRAY_BUFFER, self.source_or_color_vbo)
        glBufferData(GL_ARRAY_BUFFER, 0, self.source_or_color_vbo_data, GL_DYNAMIC_DRAW)
        glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
        glVertexAttribDivisor(3, 1)

        glEnableVertexAttribArray(4)
        glBindBuffer(GL_ARRAY_BUFFER, self.shape_vbo)
        glBufferData(GL_ARRAY_BUFFER, 0, self.shape_vbo_data, GL_DYNAMIC_DRAW)
        glVertexAttribPointer(4, 1, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
        glVertexAttribDivisor(4, 1)

        # Create vertex array object
        self.world_vao = glGenVertexArrays(1)
        glBindVertexArray(self.world_vao)

        # Vertices & texcoords
        glBindBuffer(GL_ARRAY_BUFFER, self.vertices_vbo)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(2 * vertices.itemsize))

        # Create element buffer object (EBO) for indices
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, len(indices) * 4, (GLuint * len(indices))(*indices), GL_STATIC_DRAW)

        # Atlas texture (contains images)
        self.atlas_rects, image = TextureAtlas.loadAtlas()
        self.texAtlas = self.texture(image, blur=True)

        # Font texture (contains letter images)
        #self.font_rects, image = Font.fromPNG(util.File.path("data/fonts/font.png"))
        self.font_rects, image = Font.fromSYS(None, size=30, bold=True, antialias=True, lower=True)
        self.texFont = self.texture(image)

        # Block texture (contains block images)
        self.block_rects, image = TextureAtlas.loadBlocks()
        self.texBlocks = self.texture(image, blur=True)

        # World texture (contains map data)
        self.world_size = (0, 0)
        self.texWorld = None
        
        # Instance shader
        vertPath: str = util.File.path("scripts/shaders/instance.vert")
        fragPath: str = util.File.path("scripts/shaders/instance.frag")
        self.instance_shader = Shader(vertPath, fragPath, texAtlas="int", texFont="int")
        self.instance_shader.setvar("texAtlas", 0)
        self.instance_shader.setvar("texFont", 1)
        
        # World shader
        vertPath: str = util.File.path("scripts/shaders/world.vert")
        fragPath: str = util.File.path("scripts/shaders/world.frag")
        self.world_shader = Shader(vertPath, fragPath, replace={key: value for key, (value, *_) in self.block_rects.items()}, texBlocks="int", texWorld="int", offset="vec2", resolution="int")
        self.world_shader.setvar("texBlocks", 0)
        self.world_shader.setvar("texWorld", 1)
        self.world_shader.setvar("resolution", self.camera.resolution)

    def add_vbo_instance(self, dest, source_or_color, shape):
        """
        Queue a object to be drawn on the screen and resize buffers as necessary.
        """
        if self.vbo_instances_length == self.vbo_instances_index: # Resize all instanced vbos
            if not self.vbo_instances_length:
                self.vbo_instances_length = 1
            else:
                self.vbo_instances_length *= 2

            new_dest_vbo_data = numpy.zeros(self.vbo_instances_length * 4, dtype=numpy.float32)
            new_source_or_color_vbo_data = numpy.zeros(self.vbo_instances_length * 4, dtype=numpy.float32)
            new_shape_vbo_data = numpy.zeros(self.vbo_instances_length, dtype=numpy.float32)

            new_dest_vbo_data[:len(self.dest_vbo_data)] = self.dest_vbo_data
            self.dest_vbo_data = new_dest_vbo_data
            new_source_or_color_vbo_data[:len(self.source_or_color_vbo_data)] = self.source_or_color_vbo_data
            self.source_or_color_vbo_data = new_source_or_color_vbo_data
            new_shape_vbo_data[:len(self.shape_vbo_data)] = self.shape_vbo_data
            self.shape_vbo_data = new_shape_vbo_data

            glBindBuffer(GL_ARRAY_BUFFER, self.dest_vbo)
            glBufferData(GL_ARRAY_BUFFER, self.dest_vbo_data.nbytes, self.dest_vbo_data, GL_DYNAMIC_DRAW)
 
            glBindBuffer(GL_ARRAY_BUFFER, self.source_or_color_vbo)
            glBufferData(GL_ARRAY_BUFFER, self.source_or_color_vbo_data.nbytes, self.source_or_color_vbo_data, GL_DYNAMIC_DRAW)

            glBindBuffer(GL_ARRAY_BUFFER, self.shape_vbo)
            glBufferData(GL_ARRAY_BUFFER, self.shape_vbo_data.nbytes, self.shape_vbo_data, GL_DYNAMIC_DRAW)
            
        self.dest_vbo_data[4 * self.vbo_instances_index:4 * self.vbo_instances_index + 4] = dest
        self.source_or_color_vbo_data[4 * self.vbo_instances_index:4 * self.vbo_instances_index + 4] = source_or_color
        self.shape_vbo_data[self.vbo_instances_index:self.vbo_instances_index + 1] = shape

        self.vbo_instances_index += 1

    def get_pressed_keys(self):
        keys = pygame.key.get_pressed()
        return [pygame.key.name(i).title() for i in self.key_names if keys[i]]

    def get_pressed_mods(self):
        mods = pygame.key.get_mods()
        return [self.mod_names[mod] for mod in self.mod_names if mods & mod]

    def resize(self):
        if self.fullscreen:
            flags = FULLSCREEN
        else:
            flags = DOUBLEBUF | RESIZABLE

        # Called twice, because of VSYNC...
        self.window = pygame.display.set_mode((self.width, self.height), flags=flags | OPENGL)
        self.window = pygame.display.set_mode((self.width, self.height), flags=flags | OPENGL, vsync=self.options["enableVsync"])
        glViewport(0, 0, self.width, self.height)

    def events(self):
        events = pygame.event.get()

        self.keys = {key: (value if value != 1 else 2) for key, value in self.keys.items()}
        self.unicode = ""
        self.mouse_buttons = [2 if value == 1 else value for value in self.mouse_buttons]
        self.mouse_wheel[2], self.mouse_wheel[3] = 0, 0
        
        for event in events:
            if event.type == QUIT:
                self.quit()
            elif event.type == VIDEORESIZE:
                if self.resize_supress:
                    resize_supress = False
                    continue
                self.size = event.size
                self.width, self.height = event.w, event.h
                self.resize()
            elif event.type == KEYDOWN:
                if event.unicode != "":
                    self.unicode = event.unicode
                key = pygame.key.name(event.key)
                if key in self.keys:
                    self.keys[key] = 1
            elif event.type == KEYUP:
                key = pygame.key.name(event.key)
                if key in self.keys:
                    self.keys[key] = 0
            elif event.type == MOUSEMOTION:
                self.mouse_pos = (event.pos[0] - self.width / 2, self.height / 2 - event.pos[1], event.rel[0], -event.rel[1])
            elif event.type == MOUSEBUTTONDOWN:
                if event.button < 4:
                    self.mouse_buttons[event.button - 1] = 1
            elif event.type == MOUSEBUTTONUP:
                if event.button < 4:
                    self.mouse_buttons[event.button - 1] = 0
            elif event.type == MOUSEWHEEL:
                self.mouse_wheel = [self.mouse_wheel[0] + event.x, self.mouse_wheel[1] + event.y, event.x, event.y]

    def update(self, world_data=numpy.zeros((0, 0))):
        """
        Update the window and inputs.
        """

        # Update pygame
        self.events()
        self.clock.tick(self.options["maxFps"])
        self.fps = self.clock.get_fps()
        self.delta_time = (1 / self.fps) if self.fps > 0 else self.delta_time
        
        # Reset
        glClear(GL_COLOR_BUFFER_BIT)

        # Use VAO
        glBindVertexArray(self.world_vao)

        # Use world shader
        self.world_shader.activate()

        # Send variables to shader
        self.update_world(world_data)
        self.world_shader.update()

        # Bind texture
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.texBlocks)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.texWorld)

        # Draw
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)

        # Use VAO
        glBindVertexArray(self.instance_vao)

        # Use instance shader
        self.instance_shader.activate()

        # Send variables to shader
        self.instance_shader.update()

        # Bind texture
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.texAtlas)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.texFont)

        # Send instance data to shader
        glBindBuffer(GL_ARRAY_BUFFER, self.dest_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self.dest_vbo_data.nbytes, self.dest_vbo_data)
        glBindBuffer(GL_ARRAY_BUFFER, self.source_or_color_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self.source_or_color_vbo_data.nbytes, self.source_or_color_vbo_data)
        glBindBuffer(GL_ARRAY_BUFFER, self.shape_vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self.shape_vbo_data.nbytes, self.shape_vbo_data)

        # Draw
        glDrawElementsInstanced(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None, self.vbo_instances_index)
        pygame.display.flip()

        self.vbo_instances_index = 0
        self.camera.update() # Better at the start, but currently at the end for sync of world and instanced rendering

    def toggle_fullscreen(self):
        """
        Toggle between fullscreen and normal mode.
        """
        self.fullscreen = not self.fullscreen

        self.resize_supress = True

        if self.fullscreen:
            self.pre_fullscreen = self.size
            self.width, self.height = self.size = self.screen_size
        else:
            self.width, self.height = self.size = self.pre_fullscreen

        self.resize()

    def toggle_wire_frame(self):
        """
        Toggle between drawing only outlines and filled shapes.
        """
        self.wireframe = ~self.wireframe
        if self.wireframe:
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        else:
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        
    def load_options(self):
        """
        Loads the options from the options.txt file.
        """
        options_string = """
        enableVsync: False
        maxFps: 1000
        particles: 1
        key.left: "a"
        key.right: "d"
        key.jump: "space"
        key.sprint: "left shift"
        key.return: "escape"
        """
        options = {line.split(":")[0].strip(): eval(line.split(":")[1].strip()) for line in options_string.split("\n") if line.split(":")[0].strip()}

        try:
            with open(util.File.path("data/user/options.txt"), "r") as file:
                options_string = file.read()
        except:
            ...

        for line in options_string.split("\n"):
            keyword = line.split(":")[0].strip()
            if not keyword in options or len(line.split(":")) != 2:
                continue
            value = line.split(":")[1].strip()
            if value.isdecimal():
                value = int(value)
            elif value.replace(".", "", 1).isdecimal():
                value = float(value)
            elif (value in ("True", "False") or
                  value.count("\"") == 2 and value[0] == value[-1] == "\"" or
                  value.count("'") == 2 and value[0] == value[-1] == "'"):
                value = eval(value)
            else:
                raise ValueError("Invalid value (\"" + str(value) + "\") for " + keyword)
            if ((isinstance(options[keyword], (int, bool)) and not isinstance(value, (int, bool))) or
                (isinstance(options[keyword], float) and not isinstance(value, (float, int, bool))) or
                (isinstance(options[keyword], str) and not isinstance(value, str))):
                raise ValueError("Invalid value type (\"" + str(value) + "\") for " + keyword)
            options[keyword] = value            
        return options

    def save_options(self):
        """
        Save the options in the options.txt file.
        """
        options_string = ""
        for key, value in self.options.items():
            if isinstance(value, str):
                options_string += str(key) + ": \"" + str(value) + "\"\n"
            else:
                options_string += str(key) + ": " + str(value) + "\n"

        with open(util.File.path("data/user/options.txt"), "w") as file:
            file.write(options_string)

    def keybind(self, key):
        """
        Returns the state of an action key.
        """
        return self.keys[self.options["key." + key]]

    def callback(self, function):
        if not function is None:
            function()

    def quit(self):
        """
        Quit the program
        """
        # Quit callback
        self.callback(self.callback_quit)

        # OpenGL cleanup
        glDeleteBuffers(5, (self.vertices_vbo, self.ebo, self.dest_vbo, self.source_or_color_vbo, self.shape_vbo))
        glDeleteVertexArrays(2, (self.instance_vao, self.world_vao))
        glDeleteTextures(4, (self.texAtlas, self.texFont, self.texBlocks, self.texWorld))
        self.instance_shader.delete()
        self.world_shader.delete()

        # Save options
        self.save_options()

        # Quit
        pygame.quit()
        sys.exit()
    
    def texture(self, image, blur=False):
        """
        Create a texture from an image.
        """
        data = pygame.image.tostring(image, "RGBA", 1)
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, *image.get_size(), 0, GL_RGBA, GL_UNSIGNED_BYTE, data)

        if blur:
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        else:
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        glBindTexture(GL_TEXTURE_2D, 0)
        return texture

    def update_world(self, data, blur=0):
        """
        Update the world texture.
        """
        start = (int(self.camera.pos[0]) - math.floor(self.width / 2 / self.camera.pixels_per_meter) - 2,
                 int(self.camera.pos[1]) - math.floor(self.height / 2 / self.camera.pixels_per_meter) - 2)
        chunk_start = (math.floor(start[0] / world.CHUNK_SIZE),
                       math.floor(start[1] / world.CHUNK_SIZE))
        offset = (self.camera.pos[0] % 1 + (start[0] - chunk_start[0] * world.CHUNK_SIZE) % self.camera.pixels_per_meter - self.width / (self.camera.pixels_per_meter / 2) % 1 - int(self.camera.pos[0] < 0) + 2,
                  self.camera.pos[1] % 1 + (start[1] - chunk_start[1] * world.CHUNK_SIZE) % self.camera.pixels_per_meter - self.height / (self.camera.pixels_per_meter / 2) % 1 - int(self.camera.pos[1] < 0) + 1 + 1 / self.camera.resolution)
        self.world_shader.setvar("offset", *offset) 

        # View size
        size = data.shape
        data = numpy.transpose(data) # flip axis
        if self.world_size != size:
            if not self.texWorld is None:
                glDeleteTextures(1, (self.texWorld,))
                self.texWorld = None
            self.world_size = size
        
        if self.texWorld is None: # Generate texture if necessary
            texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_R32I, *self.world_size, 0, GL_RED_INTEGER, GL_INT, data)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glBindTexture(GL_TEXTURE_2D, 0)
            self.texWorld = texture
        else: # Write world data into texture
            glBindTexture(GL_TEXTURE_2D, self.texWorld)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_R32I, *self.world_size, 0, GL_RED_INTEGER, GL_INT, data)
    
    def draw_image(self, image, position, size):
        """
        Draw an image on the window.
        """
        dest_rect = (position[0] + size[0] / 2, position[1] + size[1] / 2, size[0] / 2, size[1] / 2)
        if not self.stencil_rect is None:
            org = dest_rect[:]

            left = max(dest_rect[0] - dest_rect[2], self.stencil_rect[0] - self.stencil_rect[2])
            right = min(dest_rect[0] + dest_rect[2], self.stencil_rect[0] + self.stencil_rect[2])
            top = max(dest_rect[1] - dest_rect[3], self.stencil_rect[1] - self.stencil_rect[3])
            bottom = min(dest_rect[1] + dest_rect[3], self.stencil_rect[1] + self.stencil_rect[3])

            width = (right - left) / 2
            height = (bottom - top) / 2

            if width > 0 and height > 0:
                dest_rect = [left + width, top + height, width, height]
                self.add_vbo_instance(dest_rect, self.atlas_rects[image], 0)
        else:
            self.add_vbo_instance(dest_rect, self.atlas_rects[image], 0)

    def draw_rect(self, position, size, color):
        """
        Draw a rectangle on the window.
        """
        dest_rect = (position[0] + size[0] / 2, position[1] + size[1] / 2, size[0] / 2, size[1] / 2)
        if not self.stencil_rect is None:
            org = dest_rect[:]

            left = max(dest_rect[0] - dest_rect[2], self.stencil_rect[0] - self.stencil_rect[2])
            right = min(dest_rect[0] + dest_rect[2], self.stencil_rect[0] + self.stencil_rect[2])
            top = max(dest_rect[1] - dest_rect[3], self.stencil_rect[1] - self.stencil_rect[3])
            bottom = min(dest_rect[1] + dest_rect[3], self.stencil_rect[1] + self.stencil_rect[3])

            width = (right - left) / 2
            height = (bottom - top) / 2

            if width > 0 and height > 0:
                dest_rect = [left + width, top + height, width, height]
                self.add_vbo_instance(dest_rect, self.camera.map_color(color), 1)
        else:
            self.add_vbo_instance(dest_rect, self.camera.map_color(color), 1)

    def draw_circle(self, position, radius, color):
        """
        Draw a circle on the window.
        """
        self.add_vbo_instance((*position, radius, radius), self.camera.map_color(color), 2)

    def draw_text(self, position, text, color, size=1, centered=False, spacing=1.25):
        """
        Draw text on the window.
        """
        offset = 0

        if len(color) == 3:
            color = (*color, 255)

        if centered:
            for letter in text:
                if not letter in self.font_rects and letter.isalpha():
                    if letter.upper() in self.font_rects:
                        letter = letter.upper()
                    else:
                        letter = letter.lower()
                if not letter in self.font_rects:
                    letter = "?"
                offset -= self.font_rects[letter][1] * spacing * size

            for letter in text:
                if not letter in self.font_rects and letter.isalpha():
                    if letter.upper() in self.font_rects:
                        letter = letter.upper()
                    else:
                        letter = letter.lower()
                if not letter in self.font_rects:
                    letter = "?"
                rect = self.font_rects[letter]
                offset += rect[1] * spacing * size
                dest_rect = [position[0] + offset + rect[1], position[1], rect[1] * size, rect[2] * 2 * size]
                offset += rect[1] * spacing * size
                
                if not self.stencil_rect is None:
                    org = dest_rect[:]

                    left = max(dest_rect[0] - dest_rect[2], self.stencil_rect[0] - self.stencil_rect[2])
                    right = min(dest_rect[0] + dest_rect[2], self.stencil_rect[0] + self.stencil_rect[2])
                    top = max(dest_rect[1] - dest_rect[3], self.stencil_rect[1] - self.stencil_rect[3])
                    bottom = min(dest_rect[1] + dest_rect[3], self.stencil_rect[1] + self.stencil_rect[3])

                    width = (right - left) / 2
                    height = (bottom - top) / 2

                    if width > 0 and height > 0:
                        dest_rect = [left + width, top + height, width, height]
                        source_and_color = (color[0] + rect[0] + rect[1] * ((1 - dest_rect[2] / org[2]) if dest_rect[0] > org[0] else 0),
                                            color[1] + (round(1 - dest_rect[3] / org[3], 6) if dest_rect[1] > org[1] else 0),
                                            color[2] + rect[1] * (width / org[2]) - 0.00001,
                                            color[3] + ((height / org[3]) if (height / org[3]) < 1 else 0))
                        self.add_vbo_instance(dest_rect, source_and_color, 3)
                        
                else:
                    source_and_color = (color[0] + rect[0], color[1], color[2] + rect[1] - 0.00001, color[3])
                    self.add_vbo_instance(dest_rect, source_and_color, 3)
        else:
            for letter in text:
                if not letter in self.font_rects and letter.isalpha():
                    if letter.upper() in self.font_rects:
                        letter = letter.upper()
                    else:
                        letter = letter.lower()
                if not letter in self.font_rects:
                    letter = "?"
                rect = self.font_rects[letter]
                source_and_color = (color[0] + rect[0], color[1], color[2] + rect[1] - 0.00001, color[3])
                offset += rect[1] * spacing * size
                dest_rect = [position[0] + offset + rect[1], position[1] - rect[2] * 2, rect[1] * size, rect[2] * 2 * size]
                offset += rect[1] * spacing * size
                if not self.stencil_rect is None:
                    org = dest_rect[:]

                    left = max(dest_rect[0] - dest_rect[2], self.stencil_rect[0] - self.stencil_rect[2])
                    right = min(dest_rect[0] + dest_rect[2], self.stencil_rect[0] + self.stencil_rect[2])
                    top = max(dest_rect[1] - dest_rect[3], self.stencil_rect[1] - self.stencil_rect[3])
                    bottom = min(dest_rect[1] + dest_rect[3], self.stencil_rect[1] + self.stencil_rect[3])

                    width = (right - left) / 2
                    height = (bottom - top) / 2

                    if width > 0 and height > 0:
                        dest_rect = [left + width, top + height, width, height]
                        source_and_color = (color[0] + rect[0] + rect[1] * (1 - dest_rect[0] / org[0]), color[1] + (1 - dest_rect[1] / org[1]), color[2] + rect[1] * (width / org[2]) - 0.00001, color[3] + ((height / org[3]) if (height / org[3]) < 1 else 0))
                        self.add_vbo_instance(dest_rect, source_and_color, 3)
                else:
                    self.add_vbo_instance(dest_rect, source_and_color, 3)

class TextureAtlas:
    def __init__(self, **images):
        self.max_atlas_size = glGetIntegerv(GL_MAX_TEXTURE_SIZE)

        # Sort images with decreasing size
        self.sorted_images = sorted(images.keys(), key=lambda index: sum(images[index].get_size()), reverse=True)

        # Gather image size
        self.image_rects = [[0, 0, *images[index].get_size()] for index in self.sorted_images]
        if self.image_rects:
            self.atlas_size = list(self.image_rects[0][2:])
        else:
            self.atlas_size = [0, 0]

        # Create image coords on the texture atlas
        self.space = numpy.ones(self.atlas_size[::-1], dtype=numpy.int8)
        for index, key in enumerate(self.sorted_images):
            image = images[key]
            self.image_rects[index][:2] = self.find_empty_position(*self.image_rects[index][2:])
            for dx, dy in numpy.ndindex(*self.image_rects[index][2:]):
                x = dx + self.image_rects[index][0]
                y = dy + self.image_rects[index][1]
                self.space[y, x] = 0

        self.texture_atlas = pygame.Surface(self.atlas_size, flags=pygame.SRCALPHA)
        for index, key in enumerate(self.sorted_images):
            image = images[key]
            coord = self.image_rects[index][:2]
            self.texture_atlas.blit(image, coord)
            self.image_rects[index] = (self.image_rects[index][0] / self.atlas_size[0],
                                       self.image_rects[index][1] / self.atlas_size[1],
                                       self.image_rects[index][2] / self.atlas_size[0],
                                       self.image_rects[index][3] / self.atlas_size[1])

        self.data = pygame.image.tostring(self.texture_atlas, "RGBA", 1)

    def find_empty_position(self, width, height):
        while True:
            # Find empty space
            for x in range(self.atlas_size[0] - width + 1):
                for y in range(self.atlas_size[1] - height + 1):
                    if numpy.all(self.space[y:y+height, x:x+width] == 1):
                        return (x, y)

            # Resize space
            if self.atlas_size[0] > 2048 or self.atlas_size[1] > 2048:
                print("Warning: Atlas has a size of (2048, 2048) or higher")
            if self.atlas_size[1] > self.atlas_size[0]:
                self.space = numpy.concatenate((self.space, numpy.ones((self.space.shape[0], 1), dtype=numpy.int8)), axis=1)
                self.atlas_size[0] += 1
            else:
                self.space = numpy.concatenate((self.space, numpy.ones((1, self.space.shape[1]), dtype=numpy.int8)), axis=0)
                self.atlas_size[1] += 1

        raise Exception("Ran out of space to create texture atlas with maximum size of %d" % self.max_atlas_size)

    def loadAtlas():
        """
        Load texture atlas data from files in a folder.
        """
        with open(util.File.path("data/atlas/data.txt"), "r") as f:
            data_str = f.readlines()
        image = pygame.image.load(util.File.path("data/atlas/atlas.png"))
        rects = {}
        for line in data_str:
            if line:
                line = line.replace(" ", "")
                var, rect_str = line.split(":")
                rect = tuple([float(val) if val.replace(".", "").isdecimal()
                              and not val.replace("/", "", 1).replace(".", "").isdecimal()
                              else eval(val) for val in rect_str.split(",")]) # eval() for "1/3", otherwise float("23.2")
                rects[var] = rect
        return rects, image

    def loadBlocks():
        """
        Load block texture atlas from files in a folder.
        """
        paths = glob.glob(util.File.path("data/blocks/*.png"))
        width = math.ceil(math.sqrt(len(paths)))
        height = math.ceil(len(paths) / width)
        image = pygame.Surface((width * 16, height * 16))
        blocks = {}

        for i, path in enumerate(paths):
            y, x = divmod(i, width)
            block = os.path.basename(path).split(".")[0]
            blocks[block] = (i, x / width, 1 - y / height, 1 / width, 1 / height)
            block_surface = pygame.image.load(path)
            image.blit(block_surface, (x * 16, (height - y - 1) * 16))

        return blocks, image


class Font:
    def fromPNG(path):
        """
        Load a monospaced font from a PNG file with all letters from chr(32) to chr(96).
        """
        image = pygame.image.load(path).convert()

        letter_width = image.get_width() // 64
        letter_height = image.get_height()
        letters = {chr(i + 32): (1 / 64 * i, 1 / 64, letter_height / image.get_width()) for i in range(64)}

        return (letters, image)

    def fromTTF(path, size=1, antialias=False, lower=True):
        """
        Load a font from a TrueTypeFont file.
        """
        font = pygame.font.Font(path, size)
        images = []
        letters = {}
        if lower: # upper letters :96 | lower letters :123
            limit = 123
        else:
            limit = 96

        font_height = font.render("".join([chr(i) for i in range(32, limit)]), antialias, (0, 0, 0)).get_height()
        font_width = 0

        space = font.render("A", antialias, (0, 0, 0))

        for i in range(32, limit):
            letter = chr(i)
            if letter != " ":
                image = font.render(letter, antialias, (255, 255, 255))
            else:
                image = space
            letter_width = image.get_width()
            letters[chr(i)] = (font_width, letter_width, font_height)

            font_width += letter_width
            images.append(image)

        image = pygame.Surface((font_width, font_height))

        for letter in letters:
            image.blit(images[ord(letter) - 32], (0, letters[letter][0]))
            letters[letter] = (letters[letter][0] / font_width, letters[letter][1] / font_width, font_height / font_width)

        return (letters, image)

    def fromSYS(name, size=1, bold=False, antialias=False, lower=True):
        """
        Load a font from the system.
        """
        font = pygame.font.SysFont(name, size, bold=bold)
        images = []
        letters = {}
        if lower: # upper letters 32:96 | upper & lower letters 32:123
            limit = 123
        else:
            limit = 96

        font_height = font.render("".join([chr(i) for i in range(32, limit)]), antialias, (0, 0, 0)).get_height()
        font_width = 0

        space = font.render("A", antialias, (0, 0, 0))
        for i in range(32, limit):
            letter = chr(i)
            if letter != " ":
                image = font.render(letter, antialias, (255, 255, 255))
            else:
                image = space
            letter_width = image.get_width()
            letters[chr(i)] = (font_width, letter_width, font_height)

            font_width += letter_width
            images.append(image)
            #print(letter, i)

        image = pygame.Surface((font_width, font_height))
        for letter in letters:
            image.blit(images[ord(letter) - 32], (letters[letter][0], 0))
            letters[letter] = (letters[letter][0] / font_width, letters[letter][1] / font_width, font_height / font_width)
            #print(letters[letter][0] / font_width)

        return (letters, image)


class Shader:
    active = None

    def __init__(self, vertex, fragment, replace={}, **variables):
        self.program = glCreateProgram()
        
        with open(vertex, "r") as file:
            content = file.read()
            for search, replacement in replace.items():
                content.replace(str(search), str(replacement))
            vertex_shader = compileShader(content, GL_VERTEX_SHADER)
        with open(fragment, "r") as file:
            fragment_shader = compileShader(file.read(), GL_FRAGMENT_SHADER)
        glAttachShader(self.program, vertex_shader)
        glAttachShader(self.program, fragment_shader)
        glLinkProgram(self.program)
        glValidateProgram(self.program)
        glDeleteShader(vertex_shader)
        glDeleteShader(fragment_shader)

        # Dict containing all variables which should be send to the fragment shader {variable1: (uniformLoc, glUniformFunc, value)}
        self.variables = {variable: Shader.get_uniform_loc(self.program, variable, variables[variable]) for variable in variables}

    def setvar(self, variable, *value):
        """
        Set the value of a variable, which is send to the shader by update
        """
        self.variables[variable][2] = value

    def activate(self):
        """
        Activate the shader.
        """
        glUseProgram(self.program)
        Shader.active = self

    def delete(self):
        """
        Delete the shader.
        """
        glDeleteProgram(self.program)

    def get_uniform_loc(program, variable, data_type): # Get location and convert glsl data type to valid function
        loc = glGetUniformLocation(program, variable)
        func = data_type_map = {'int': glUniform1i,
                                'uint': glUniform1ui,
                                'float': glUniform1f,
                                'vec2': glUniform2f,
                                'vec3': glUniform3f,
                                'vec4': glUniform4f,
                                'bvec2': glUniform2i,
                                'bvec3': glUniform3i,
                                'bvec4': glUniform4i,
                                'ivec2': glUniform2i,
                                'ivec3': glUniform3i,
                                'ivec4': glUniform4i,
                                'uvec2': glUniform2ui,
                                'uvec3': glUniform3ui,
                                'uvec4': glUniform4ui,
                                'mat2': glUniformMatrix2fv,
                                'mat3': glUniformMatrix3fv,
                                'mat4': glUniformMatrix4fv}[data_type]
        return [loc, func, None]

    def update(self):
        """
        Update all variables.
        """
        for index, (loc, func, value) in self.variables.items():
            if value is None:
                continue
            func(loc, *value)
            self.variables[index][2] = None


class Camera:
    def __init__(self, window):
        self.resolution: int = 2 # currently only working with 1 & 2
        self.pixels_per_meter: int = self.resolution * 16
        self.threshold = 0.1

        self.pos: [float] = [0, 0]
        self.vel: [float] = [0, 0]
        self.dest: [float] = [0, 0]
        self.window: Window = window

    def set(self, pos):
        """
        Set the camera position.
        Use move() for slow movement.
        """
        self.pos = pos
        self.vel = [0, 0]
        self.dest = pos

    def move(self, pos: [float]):
        """
        Move the camera slowly to a position.
        Use set() for instant movement.
        """
        self.dest = pos

    def update(self):
        """
        Update the camera.
        """
        xvel = round((self.dest[0] - self.pos[0]) / 10, 3)
        yvel = round((self.dest[1] - self.pos[1]) / 10, 3)

        xvel = math.copysign(max(abs(xvel) - self.threshold, 0), xvel)
        yvel = math.copysign(max(abs(yvel) - self.threshold, 0), yvel)

        self.vel[0] = xvel
        self.vel[1] = yvel
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]

    def map_coord(self, coord: [float], from_pixel: bool=True, from_centered: bool=True, from_world: bool=False, pixel: bool=False, centered: bool=True, world: bool=False):
        """
        Convert a coordinate to a different format.
        Current format specified by from_pixel, from_centered, from_world.
        Output format specified by pixel, centered, world.
        """
        if from_world:
            from_pixel = True
        if world:
            pixel = True
        coord = list(coord)

        if from_world and not world:
            for i in range(len(coord)):
                if i < 2:
                    coord[i] = (coord[i] - self.pos[i]) * self.pixels_per_meter
                else:
                    coord[i] = coord[i] * self.pixels_per_meter
        elif (not from_world) and world:
            for i in range(len(coord)):
                coord[i] = coord[i] / self.pixels_per_meter + self.pos[i % 2]

        if from_pixel and not pixel:
            for i in range(len(coord)):
                coord[i] /= (self.window.width, self.window.height)[i%2] / 2
        elif (not from_pixel) and pixel:
            for i in range(len(coord)):
                coord[i] /= (self.window.width, self.window.height)[i%2] / 2

        if (not from_centered) and centered:
            for i in range(2):
                coord[i] -= 1
        elif from_centered and not centered:
            for i in range(2):
                coord[i] += 1

        return coord

    def map_color(self, color):
        if not float in color:
            color = [i / 255 for i in color]
        if len(color) == 3:
            color = (*color, 1)
        return color

    def visible_blocks(self):
        center = (int(self.pos[0]),
                  int(self.pos[1]))
        start = (center[0] - math.floor(self.window.width / 2 / self.pixels_per_meter) - 2,
                 center[1] - math.floor(self.window.height / 2 / self.pixels_per_meter) - 2)
        end = (center[0] + math.ceil(self.window.width / 2 / self.pixels_per_meter) + 2,
               center[1] + math.ceil(self.window.height / 2 / self.pixels_per_meter) + 2)
        return start, end