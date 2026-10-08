// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title VehicleRegistry
/// @author Angelo David Padilla Romero
/// @notice An append-only, tamper-evident lifecycle log for vehicles.
/// @dev Each vehicle is a bytes32 id (a hash of its VIN), so no VIN or personal
///      data reaches the chain. Authorised recorders append events — services,
///      inspections, part replacements, ownership transfers, odometer readings,
///      and incidents — each carrying an odometer value, a timestamp, and the
///      keccak digest of the full off-chain record. The chain never rejects a
///      suspicious value (a lower odometer than before is exactly what fraud
///      looks like); it preserves the complete, immutable history so the
///      off-chain analyser can flag anomalies against a trustworthy record.
contract VehicleRegistry {
    enum EventType {
        SERVICE,
        INSPECTION,
        PART_REPLACEMENT,
        OWNERSHIP_TRANSFER,
        ODOMETER_READING,
        INCIDENT
    }

    struct VehicleEvent {
        EventType eventType;
        uint256 odometerKm;
        uint64 timestamp;
        bytes32 dataHash; // digest of the off-chain record detail
        address recorder;
    }

    address public operator;
    uint256 public totalEvents;

    mapping(address => bool) public isRecorder;
    mapping(bytes32 => VehicleEvent[]) private _history;

    event RecorderSet(address indexed recorder, bool allowed);
    event EventRecorded(
        bytes32 indexed vehicleId,
        uint256 indexed index,
        EventType eventType,
        uint256 odometerKm,
        uint64 timestamp,
        bytes32 dataHash,
        address recorder
    );
    event OperatorTransferred(address indexed previousOperator, address indexed newOperator);

    error NotOperator();
    error NotRecorder();
    error ZeroVehicle();

    modifier onlyOperator() {
        if (msg.sender != operator) revert NotOperator();
        _;
    }

    constructor() {
        operator = msg.sender;
        isRecorder[msg.sender] = true;
        emit OperatorTransferred(address(0), msg.sender);
        emit RecorderSet(msg.sender, true);
    }

    function transferOperator(address newOperator) external onlyOperator {
        if (newOperator == address(0)) revert ZeroVehicle();
        address previous = operator;
        operator = newOperator;
        emit OperatorTransferred(previous, newOperator);
    }

    /// @notice Authorise or revoke an address that may append events (a workshop,
    ///         inspection centre, or the passport service).
    function setRecorder(address recorder, bool allowed) external onlyOperator {
        isRecorder[recorder] = allowed;
        emit RecorderSet(recorder, allowed);
    }

    /// @notice Append one lifecycle event for a vehicle.
    /// @return index the position of the new event in the vehicle's history.
    function recordEvent(
        bytes32 vehicleId,
        EventType eventType,
        uint256 odometerKm,
        uint64 timestamp,
        bytes32 dataHash
    ) external returns (uint256 index) {
        if (!isRecorder[msg.sender]) revert NotRecorder();
        if (vehicleId == bytes32(0)) revert ZeroVehicle();

        VehicleEvent[] storage events = _history[vehicleId];
        index = events.length;
        events.push(
            VehicleEvent({
                eventType: eventType,
                odometerKm: odometerKm,
                timestamp: timestamp,
                dataHash: dataHash,
                recorder: msg.sender
            })
        );
        totalEvents += 1;

        emit EventRecorded(
            vehicleId, index, eventType, odometerKm, timestamp, dataHash, msg.sender
        );
    }

    function eventCount(bytes32 vehicleId) external view returns (uint256) {
        return _history[vehicleId].length;
    }

    function getEvent(bytes32 vehicleId, uint256 index)
        external
        view
        returns (
            EventType eventType,
            uint256 odometerKm,
            uint64 timestamp,
            bytes32 dataHash,
            address recorder
        )
    {
        VehicleEvent memory e = _history[vehicleId][index];
        return (e.eventType, e.odometerKm, e.timestamp, e.dataHash, e.recorder);
    }

    /// @notice The most recent odometer reading recorded for a vehicle (0 if none).
    function lastOdometer(bytes32 vehicleId) external view returns (uint256) {
        VehicleEvent[] storage events = _history[vehicleId];
        if (events.length == 0) return 0;
        return events[events.length - 1].odometerKm;
    }
}
