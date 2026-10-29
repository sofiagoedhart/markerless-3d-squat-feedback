using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;
using SimpleJSON;

public class PoseUdpReceiver : MonoBehaviour
{
    public int port = 5006;
    [Tooltip("Seconds without a packet before the stream is treated as dead.")]
    public float staleAfter = 1.0f;

    public JSONNode Latest { get; private set; }
    /// The last completed rep.
    public JSONNode LastRep { get; private set; }
    public int RepSequence { get; private set; }

    /// Every completed rep of the current set, in order.
    public List<JSONNode> SetReps { get; } = new List<JSONNode>();

    /// Forget the current set's reps and start collecting again.
    public void ClearSet() { SetReps.Clear(); _setOpen = true; }

    /// Stop collecting, without discarding what is there.
    public void CloseSet() { _setOpen = false; }

    bool _setOpen = true;
    public int PacketCount { get; private set; }
    public float LastPacketTime { get; private set; }
    public bool IsLive => Latest != null && (Time.time - LastPacketTime) < staleAfter;

    readonly object _lock = new object();
    const int MaxQueued = 256;
    readonly Queue<string> _pending = new Queue<string>();
    readonly List<string> _drain = new List<string>();
    Thread _thread;
    UdpClient _client;
    bool _run;

    void OnEnable()
    {
        try
        {
            _client = new UdpClient(port);
            _client.Client.ReceiveTimeout = 500;
        }
        catch (Exception e)
        {
            Debug.LogError($"[PoseUdpReceiver] could not bind UDP {port}: {e.Message}. " +
                           "Another copy of the scene or a stray Play session is probably still holding it.");
            enabled = false;
            return;
        }
        _run = true;
        _thread = new Thread(Loop) { IsBackground = true };
        _thread.Start();
        Debug.Log($"[PoseUdpReceiver] listening on 127.0.0.1:{port}");
    }

    void OnDisable()
    {
        _run = false;
        try { _client?.Close(); } catch { }
        try { _thread?.Join(500); } catch { }
        _client = null; _thread = null;
    }

    void Loop()
    {
        var any = new IPEndPoint(IPAddress.Any, 0);
        while (_run)
        {
            try
            {
                byte[] data = _client.Receive(ref any);
                string s = System.Text.Encoding.UTF8.GetString(data);
                lock (_lock)
                {
                    _pending.Enqueue(s);
                    while (_pending.Count > MaxQueued) _pending.Dequeue();
                }
            }
            catch (SocketException) {  }
            catch (ObjectDisposedException) { break; }
            catch (Exception e) { Debug.LogWarning("[PoseUdpReceiver] " + e.Message); }
        }
    }

    void Update()
    {
        _drain.Clear();
        lock (_lock) { while (_pending.Count > 0) _drain.Add(_pending.Dequeue()); }
        if (_drain.Count == 0) return;

        for (int i = 0; i < _drain.Count; i++)
        {
            try
            {
                JSONNode pkt = JSON.Parse(_drain[i]);
                JSONNode rep = pkt["rep"];
                if (rep != null && !rep.IsNull)
                {
                    LastRep = rep;
                    if (_setOpen) SetReps.Add(rep);
                    RepSequence++;
                }
                Latest = pkt;
                PacketCount++;
                LastPacketTime = Time.time;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PoseUdpReceiver] bad packet: " + e.Message);
            }
        }
    }
}
