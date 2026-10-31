// SPDX-License-Identifier: Apache-2.0
// Metadata-only probe using the pinned samloader-rs API. No IMEI and no download.
use samloader_fus::FusClient;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert!(args.len() == 3, "usage: beyoud_probe MODEL CSC");
    let mut client = FusClient::new().expect("SmartDownload handshake failed");
    let history = client.fetch_history(&args[1], &args[2])
        .or_else(|_| samloader_fus::fetch_version_xml(&args[1], &args[2]))
        .expect("No firmware version available for configured model/CSC");
    assert!(!history.latest.is_empty(), "Empty firmware version");
    println!("Checking model={} CSC={} version={}", args[1], args[2], history.latest);
    client.fetch_binary_info(&args[1], &args[2], &history.latest);
    assert!(client.info.size > 0, "Empty firmware binary");
    assert!(!client.info.filename.is_empty(), "Firmware filename missing");
    println!("BEYOUD_FIRMWARE\t{}\t{}\t{}\t{}", args[1], args[2], client.info.version, client.info.size);
    println!("SmartDownload metadata accepted: version={} size={} bytes", client.info.version, client.info.size);
}
