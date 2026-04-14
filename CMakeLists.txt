cmake_minimum_required(VERSION 4.1)
project(wyreplumber C)

set(CMAKE_C_STANDARD 11)

find_package(Python3 REQUIRED COMPONENTS Development)
find_package(PkgConfig REQUIRED)
pkg_check_modules(PIPEWIRE REQUIRED libpipewire-0.3)
pkg_check_modules(WIREPLUMBER REQUIRED wireplumber-0.4)

add_library(wyreplumber_core MODULE
        native/wyreplumber.c
        native/wp_connection/wp_connection.c
        native/wp_connection/wp_connection.h
        native/wp_connection/get_nodes.c
        native/wp_connection/get_modules.c
        native/wp_connection/get_metadata.c
        native/wp_connection/load_module.c
        native/wp_connection/sync.c
        native/wp_node/wp_node.c
        native/wp_module/wp_module.h
        native/wp_module/wp_module.c
        native/wp_port/wp_port.c
        native/wp_metadata/wp_metadata.c
        native/wp_metadata/metadata_find.c
        native/wp_metadata/metadata_set.c
        native/wp_metadata/metadata_clear.c
        native/wp_metadata/metadata_iterate.c
        native/wp_pipewire_object/wp_pipewire_object.c
        native/wp_pipewire_object/wp_pipewire_object.c)


target_include_directories(wyreplumber_core PRIVATE
        ${Python3_INCLUDE_DIRS}
        ${PIPEWIRE_INCLUDE_DIRS}
        ${WIREPLUMBER_INCLUDE_DIRS}
        native
)

target_compile_options(wyreplumber_core PRIVATE
        ${PIPEWIRE_CFLAGS_OTHER}
        ${WIREPLUMBER_CFLAGS_OTHER}
)

target_link_directories(wyreplumber_core PRIVATE
        ${PIPEWIRE_LIBRARY_DIRS}
        ${WIREPLUMBER_LIBRARY_DIRS}
)

target_link_libraries(wyreplumber_core PRIVATE
        Python3::Python
        ${PIPEWIRE_LIBRARIES}
        ${WIREPLUMBER_LIBRARIES}
)