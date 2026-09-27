add_executable(zipline-ride-tests
    zipline_ride_tests.cpp
    ../source/MapNavigator/zipline_ride_machine.cpp
    ../source/MapNavigator/navi_math.cpp)
target_include_directories(zipline-ride-tests PRIVATE ../source ${MAA_PRIVATE_INC} ${MAA_PUBLIC_INC})
target_link_libraries(zipline-ride-tests PRIVATE MaaUtils ${OpenCV_LIBS})
add_test(NAME zipline-segment-handoff COMMAND zipline-ride-tests)

add_executable(fixed-zipline-tests fixed_zipline_tests.cpp ../source/MapNavigator/zipline_ride_machine.cpp ../source/MapNavigator/navi_math.cpp)
target_include_directories(fixed-zipline-tests PRIVATE ../source ${MAA_PRIVATE_INC} ${MAA_PUBLIC_INC})
target_link_libraries(fixed-zipline-tests PRIVATE MaaUtils ${OpenCV_LIBS})
add_test(NAME fixed-zipline-contract COMMAND fixed-zipline-tests "${CMAKE_CURRENT_SOURCE_DIR}/../../../assets/data/MapNavigator/fixed_zipline_routes.json")

if(WIN32)
    set_tests_properties(zipline-segment-handoff fixed-zipline-contract PROPERTIES
        ENVIRONMENT_MODIFICATION "PATH=path_list_prepend:${DEPS_DIR}/bin;PATH=path_list_prepend:${MAADEPS_DIR}/vcpkg/installed/${MAADEPS_TRIPLET}/bin")
endif()
