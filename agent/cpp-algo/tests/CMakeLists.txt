add_executable(zipline-ride-tests
    zipline_ride_tests.cpp
    ../source/MapNavigator/zipline_ride_machine.cpp
    ../source/MapNavigator/navi_math.cpp)
target_include_directories(zipline-ride-tests PRIVATE ../source ${MAA_PRIVATE_INC} ${MAA_PUBLIC_INC})
target_link_libraries(zipline-ride-tests PRIVATE MaaUtils ${OpenCV_LIBS})
add_test(NAME zipline-segment-handoff COMMAND zipline-ride-tests)
