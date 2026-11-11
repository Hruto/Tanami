import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';

void main() {
  testWidgets('Tanami app renders correctly', (WidgetTester tester) async {
    await tester.pumpWidget(const TanamiApp());

    expect(find.text('Welcome to Tanami'), findsOneWidget);
  });
}