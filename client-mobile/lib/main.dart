import "package:flutter/material.dart";

import "list_screen.dart";

void main() {
  runApp(const WhaleSightingsApp());
}

class WhaleSightingsApp extends StatelessWidget {
  const WhaleSightingsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Whale Sightings",
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue)),
      home: const ListScreen(),
    );
  }
}
