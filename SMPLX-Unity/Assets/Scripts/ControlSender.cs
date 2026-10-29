using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

public class ControlSender : MonoBehaviour
{
    [Tooltip("Where live_form_feedback.py listens (--control-port).")]
    public int port = 5007;
    public string host = "127.0.0.1";
    public bool logSends = true;

    UdpClient _client;
    IPEndPoint _to;

    void OnEnable()
    {
        try
        {
            _client = new UdpClient();
            _to = new IPEndPoint(IPAddress.Parse(host), port);
        }
        catch (Exception e)
        {
            Debug.LogWarning("[ControlSender] " + e.Message);
            enabled = false; return;
        }
        SessionSettings.Changed += Send;
        Send();
    }

    void OnDisable()
    {
        SessionSettings.Changed -= Send;
        try { _client?.Close(); } catch { }
        _client = null;
    }

    /// Tells Python the athlete pressed Start.
    public void SendStart() => Raw("{\"cmd\":\"start\"}");

    /// Tells Python the set has ended.
    public void SendEndSet() => Raw("{\"cmd\":\"endset\"}");

    /// Tells Python to start the pre-calibration countdown (Enter on the setup skeleton screen).
    public void SendCalibrate() => Raw("{\"cmd\":\"calibrate\"}");

    public void Send()
    {
        if (_client == null) return;
        Raw("{\"target\":\"" + SessionSettings.DepthTarget + "\"," +
            "\"reps\":" + SessionSettings.RepTarget + "}");
    }

    void Raw(string json)
    {
        if (_client == null) return;
        try
        {
            byte[] b = Encoding.UTF8.GetBytes(json);
            _client.Send(b, b.Length, _to);
            if (logSends) Debug.Log("[ControlSender] " + json);
        }
        catch (Exception e)
        {
            Debug.LogWarning("[ControlSender] send failed: " + e.Message);
        }
    }
}
